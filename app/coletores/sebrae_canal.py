"""
Coletor do Canal do Fornecedor do Sebrae (scf3.sebrae.com.br/portalcf), onde
todo o Sistema Sebrae publica as licitações e chamadas públicas.

A tabela da página é preenchida por Licitacoes/GetLicitacoesGrid (JSON no
formato do DataTables), que devolve 12 processos por vez; o filtro e a página
atual ficam na sessão do site. Por isso o coletor abre a página no Playwright
e clica em ">" guardando cada resposta, como uma pessoa faria. A lista padrão
já vem só com processos "Em andamento" (diagnóstico de 28/09/2026).

A lista é nacional: cada fonte (uma por estado) separa os seus processos pelas
'marcas' do config.yaml (ex.: "SEBRAE-MG" no número, "MINAS GERAIS" na
unidade). As fontes de uma mesma coleta reaproveitam a lista já lida.
"""
from __future__ import annotations

import json
import logging
import time

from playwright.sync_api import sync_playwright

from ..filtro import normalizar
from .base import USER_AGENT, Coletor, Edital
from .paradigma_api import parse_data_portal

log = logging.getLogger(__name__)

URL_PADRAO = "https://www.scf3.sebrae.com.br/portalcf/Licitacoes"
URL_DETALHE = "https://www.scf3.sebrae.com.br/portalcf/Licitacoes/Detalhe?Id={}"
VALIDADE_CACHE = 30 * 60  # segundos: cobre as três fontes de uma mesma coleta

_cache: dict[str, tuple[float, list[dict]]] = {}


def _texto(v) -> str:
    return " ".join(str(v or "").split())


def _primeiro(reg: dict, *chaves: str) -> str:
    for c in chaves:
        t = _texto(reg.get(c))
        if t and t.lower() not in ("nenhum", "null"):
            return t
    return ""


def do_estado(reg: dict, marcas: list[str]) -> bool:
    """O processo é do estado se alguma marca aparece em qualquer campo de texto
    (número "CP/002-SEBRAE-MG-2026", unidade "SEBRAE MINAS GERAIS"...)."""
    texto = normalizar(json.dumps(reg, ensure_ascii=False))
    return any(normalizar(m) in texto for m in marcas)


def registro_para_edital(reg: dict, fonte_nome: str, uf: str) -> Edital | None:
    ident = _texto(reg.get("Id"))
    numero = _primeiro(reg, "Numero", "NumeroProcesso")
    objeto = _primeiro(reg, "Objeto")
    if not ident or not (numero or objeto):
        return None
    return Edital(
        fonte=fonte_nome,
        id_externo=ident,
        titulo=numero or objeto[:140],
        objeto=objeto,
        url=URL_DETALHE.format(ident),
        unidade=_primeiro(reg, "SebraeDescricao", "SebraeNome", "NomeSebrae", "Unidade",
                          "UnidadeDescricao") or f"Sebrae/{uf}",
        tipo=_primeiro(reg, "ModalidadeDescricao", "ModalidadeNome", "DescricaoModalidade"),
        situacao=_primeiro(reg, "StatusDescricao", "SituacaoDescricao"),
        data_publicacao=parse_data_portal(reg.get("DataPublicacao")),
        # só chamadas de credenciamento trazem data final; nas outras, o prazo
        # fica no edital (a data de abertura é a da sessão, não a de inscrição)
        prazo=parse_data_portal(reg.get("DataCredenciamentoFim") or reg.get("DataEncerramento")),
    )


class ColetorSebraeCanal(Coletor):
    def coletar(self) -> list[Edital]:
        uf = self.fonte.get("uf", "")
        marcas = self.fonte.get("marcas") or [f"SEBRAE-{uf}", f"SEBRAE/{uf}"]
        registros = self._registros()
        editais: dict[str, Edital] = {}
        for reg in registros:
            if not do_estado(reg, marcas):
                continue
            try:
                ed = registro_para_edital(reg, self.nome, uf)
            except Exception as e:  # um registro estranho não derruba a fonte
                log.warning("Registro ignorado (%s): %s", e, reg.get("Id"))
                continue
            if ed:
                editais[ed.chave] = ed
        log.info("%s: %d de %d processos do Canal do Fornecedor", self.nome,
                 len(editais), len(registros))
        return list(editais.values())

    def _registros(self) -> list[dict]:
        url = self.url or URL_PADRAO
        guardado = _cache.get(url)
        if guardado and time.monotonic() - guardado[0] < VALIDADE_CACHE:
            self.progresso.passo(f"{len(guardado[1])} processos já lidos nesta coleta")
            return guardado[1]
        registros = self._ler_grade(url)
        _cache[url] = (time.monotonic(), registros)
        return registros

    def _ler_grade(self, url: str) -> list[dict]:
        max_paginas = int(self.fonte.get("max_paginas", 60))
        vistos: dict[str, dict] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                self.progresso.passo("Abrindo o Canal do Fornecedor", 0, max_paginas)
                with page.expect_response(lambda r: "GetLicitacoesGrid" in r.url,
                                          timeout=self.timeout_ms()) as resp:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms())
                novos = self._guardar(resp.value, vistos)
                for pagina in range(2, max_paginas + 1):
                    proxima = page.get_by_role("link", name=">", exact=True)
                    if not novos or not proxima.count():
                        break
                    self.progresso.passo(f"Página {pagina} ({len(vistos)} processos)",
                                         pagina - 1, max_paginas)
                    with page.expect_response(lambda r: "GetLicitacoesGrid" in r.url,
                                              timeout=self.timeout_ms()) as resp:
                        proxima.first.click(timeout=self.timeout_ms())
                    if pagina == 2:  # como o site pede a página seguinte
                        log.info("Canal do Fornecedor, página 2: %s %s", resp.value.url,
                                 resp.value.request.post_data)
                    novos = self._guardar(resp.value, vistos)
            finally:
                browser.close()
        return list(vistos.values())

    @staticmethod
    def _guardar(resposta, vistos: dict[str, dict]) -> int:
        """Guarda os processos da resposta; devolve quantos eram novos."""
        dados = resposta.json()
        antes = len(vistos)
        for reg in dados.get("aaData") or []:
            if reg.get("Id") is not None:
                vistos.setdefault(str(reg["Id"]), reg)
        if antes == 0 and vistos:
            primeiro = next(iter(vistos.values()))
            log.info("Canal do Fornecedor: campos %s", sorted(primeiro))
        return len(vistos) - antes
