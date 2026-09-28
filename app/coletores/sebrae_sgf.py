"""
Coletor do SGF, o Sistema de Gestão de Fornecedores do Sebrae
(sgf.sebrae.com.br), onde os Sebrae estaduais publicam os editais de
credenciamento de consultoria e instrutoria. O Sebrae/RJ usa o SGF, e o SOMA
do Sebrae-SP manda as inscrições para ele (diagnóstico de 28/09/2026).

É um site ASP.NET WebForms: a lista (10 editais por vez) já abre com a
situação "Aberto" e todos os estados. Trocar o estado no filtro fez a lista
sumir no teste de 28/09/2026, então o coletor percorre a lista nacional
(poucas páginas: só editais abertos), separa os estados pela coluna UF e
guarda o resultado para as outras fontes da mesma coleta.
"""
from __future__ import annotations

import logging
import time

from playwright.sync_api import sync_playwright

from ..filtro import normalizar
from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)

URL_PADRAO = "https://sgf.sebrae.com.br/Home/"
VALIDADE_CACHE = 30 * 60  # segundos: cobre as fontes de uma mesma coleta

_cache: dict[str, tuple[float, list[dict]]] = {}

# Linhas da grade: células visíveis e links que não são postback
JS_LINHAS = """
tab => [...tab.querySelectorAll('tr')].map(tr => ({
  th: [...tr.querySelectorAll('th')].map(c => (c.innerText || '').split('\\n')[0].trim()),
  td: [...tr.querySelectorAll('td')].map(c => (c.innerText || '').trim()),
  links: [...tr.querySelectorAll('a[href]')].map(a => a.href)
           .filter(h => h && !h.startsWith('javascript')),
}))
"""


def linhas_para_editais(linhas: list[dict], fonte_nome: str, uf: str,
                        url_padrao: str) -> list[Edital]:
    cabecalho: list[str] = []
    editais = []
    for ln in linhas:
        if ln["th"]:
            cabecalho = [normalizar(h) for h in ln["th"]]
            continue
        cel = ln["td"]
        if not cabecalho or len(cel) < 3:
            continue  # paginação e linhas vazias

        def campo(*nomes: str) -> str:
            for nome in nomes:
                if nome in cabecalho and cabecalho.index(nome) < len(cel):
                    return cel[cabecalho.index(nome)]
            return ""

        estado, codigo, titulo = campo("uf"), campo("codigo"), campo("titulo")
        if not codigo or not titulo or (estado and estado.upper() != uf):
            continue
        inscricao = [h for h in ln["links"] if "inscricao" in h.lower()]
        editais.append(Edital(
            fonte=fonte_nome,
            id_externo=codigo,
            titulo=f"{codigo}: {titulo}",
            objeto=titulo,
            url=(inscricao or ln["links"] or [url_padrao])[0],
            unidade=f"Sebrae/{uf}",
            tipo="Credenciamento",
            situacao=campo("status"),
            data_publicacao=parse_data(campo("data da publicacao")),
        ))
    return editais


class ColetorSebraeSgf(Coletor):
    def coletar(self) -> list[Edital]:
        uf = self.fonte["uf"]
        url = self.url or URL_PADRAO
        editais = {ed.chave: ed
                   for ed in linhas_para_editais(self._linhas(url), self.nome, uf, url)}
        log.info("%s: %d editais", self.nome, len(editais))
        return list(editais.values())

    def _linhas(self, url: str) -> list[dict]:
        guardado = _cache.get(url)
        if guardado and time.monotonic() - guardado[0] < VALIDADE_CACHE:
            return guardado[1]
        linhas = self._ler_lista(url)
        _cache[url] = (time.monotonic(), linhas)
        return linhas

    def _ler_lista(self, url: str) -> list[dict]:
        max_paginas = int(self.fonte.get("max_paginas", 15))
        linhas: list[dict] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                self.progresso.passo("Abrindo o SGF", 0, max_paginas)
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms())
                for pagina in range(1, max_paginas + 1):
                    self.progresso.passo(f"Página {pagina}", pagina, max_paginas)
                    grade = page.query_selector("table[id$='gvEdital']")
                    if not grade:
                        texto = " ".join(page.inner_text("body").split())[:300]
                        raise RuntimeError(f"a lista de editais do SGF não apareceu: {texto}")
                    atuais = grade.evaluate(JS_LINHAS)
                    linhas += atuais
                    proxima = page.locator("a[href*='ibtnNext']")
                    if not proxima.count():
                        break
                    antes = grade.inner_text()
                    proxima.first.click(timeout=self.timeout_ms())
                    try:  # postback: completo ou parcial (UpdatePanel); espera a grade mudar
                        page.wait_for_function(
                            """antes => {
                                 const t = document.querySelector("table[id$='gvEdital']");
                                 return t && t.innerText !== antes;
                               }""", arg=antes, timeout=20000)
                    except Exception:
                        log.info("SGF: a página %d não mudou; fim da lista", pagina + 1)
                        break
            finally:
                browser.close()
        return linhas
