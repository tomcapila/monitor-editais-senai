"""
Coletor da API pública de licitações do "Sistema Transparência" do SESI/SENAI
(sistematransparenciaweb.com.br), usada pela página de transparência do
SENAI-SP. É a mesma fonte dos botões "Salvar em XLSX" daquela página.

Cada consulta devolve os processos de um ano (algumas centenas). Um processo
aberto num ano não reaparece na lista do ano seguinte, por isso o coletor
consulta os últimos 'anos' anos (diagnóstico de 28/09/2026).

A API não traz link nem prazo. O link padrão é a página de transparência; se
ela listar documentos do processo (DocumentosSap?id=<idLicitacao>), o link
passa a ser o PDF do edital, que a coleta então lê em busca do prazo.
"""
from __future__ import annotations

import logging
from datetime import date
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)

URL_API = "https://sistematransparenciaweb.com.br/api-licitacoes/publico/licitacoes"


def _texto(v) -> str:
    return " ".join(str(v or "").split())


def documentos_por_processo(html: str, base: str) -> dict[str, str]:
    """{idLicitacao: link do PDF} a partir dos links DocumentosSap da página.
    Quando um processo tem vários arquivos, prefere o que não é ata."""
    docs: dict[str, str] = {}
    atas: set[str] = set()  # processos cujo link guardado até agora é uma ata
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base, a["href"])
        if "documentossap" not in href.lower():
            continue
        ident = (parse_qs(urlsplit(href).query).get("id") or [""])[0]
        if not ident:
            continue
        eh_ata = a.get_text(" ", strip=True).lower().startswith("ata")
        if ident not in docs or (ident in atas and not eh_ata):
            docs[ident] = href
            atas.discard(ident)
            if eh_ata:
                atas.add(ident)
    return docs


def registro_para_edital(reg: dict, fonte_nome: str, link_padrao: str,
                         documentos: dict[str, str] | None = None) -> Edital | None:
    ident = _texto(reg.get("idLicitacao")) or _texto(reg.get("codigoLicitacao"))
    titulo = _texto(reg.get("titulo"))
    if not ident or not titulo:
        return None
    situacao = _texto(reg.get("statusLicitacao"))
    # dataAbertura é a abertura da disputa (ou o início, num credenciamento):
    # não é publicação nem prazo de inscrição, então vai como texto na situação
    abertura = parse_data(_texto(reg.get("dataAbertura")))
    if abertura and abertura.year > 1900:
        situacao = f"{situacao} · abertura em {abertura:%d/%m/%Y}".lstrip(" ·")
    # "000000473/2026" -> "473/2026", o número que o SENAI-SP usa nos editais
    numero = _texto(reg.get("numero")).lstrip("0")
    return Edital(
        fonte=fonte_nome,
        id_externo=ident,
        titulo=f"Nº {numero}: {titulo}" if numero else titulo,
        objeto=_texto(reg.get("objeto")),
        url=(documentos or {}).get(ident) or f"{link_padrao}#processo-{ident}",
        unidade=_texto(reg.get("entidadeRegional")) or _texto(reg.get("nmEmpresa")),
        tipo=_texto(reg.get("modalidade")),
        situacao=situacao,
    )


class ColetorSistemaTransparencia(Coletor):
    def coletar(self) -> list[Edital]:
        api = self.fonte.get("api") or URL_API
        pagina = self.url  # página pública de transparência (link e documentos)
        anos = int(self.fonte.get("anos", 2))
        ano_atual = date.today().year
        cabecalhos = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        total = anos + 1

        documentos: dict[str, str] = {}
        if pagina:
            self.progresso.passo("Lendo os documentos da página de transparência", 0, total)
            try:
                r = httpx.get(pagina, timeout=self.timeout_ms() / 1000,
                              follow_redirects=True, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
                documentos = documentos_por_processo(r.text, str(r.url))
            except httpx.HTTPError as e:
                # sem os PDFs, os processos ficam com o link da página
                log.warning("Página de transparência indisponível (%s): %s", pagina, e)

        resultados: dict[str, Edital] = {}
        for i, ano in enumerate(range(ano_atual, ano_atual - anos, -1), start=1):
            self.progresso.passo(f"Processos de {ano}", i, total)
            params = {"ano": ano, "departamento": self.fonte["departamento"],
                      "entidade": self.fonte["entidade"]}
            r = httpx.get(api, params=params, timeout=self.timeout_ms() / 1000,
                          follow_redirects=True, headers=cabecalhos)
            r.raise_for_status()
            registros = r.json()
            for reg in registros:
                try:
                    ed = registro_para_edital(reg, self.nome, pagina or api, documentos)
                except Exception as e:  # um registro estranho não derruba a fonte
                    log.warning("Registro ignorado (%s): %s", e, reg.get("idLicitacao"))
                    continue
                # o mesmo processo pode vir em mais de um ano: vale o mais recente
                if ed and ed.chave not in resultados:
                    resultados[ed.chave] = ed
            log.info("%s %d: %d processos", self.nome, ano, len(registros))
        self.progresso.passo(f"{len(resultados)} processos lidos", total, total)
        return list(resultados.values())
