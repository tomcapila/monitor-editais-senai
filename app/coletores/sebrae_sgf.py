"""
Coletor do SGF, o Sistema de Gestão de Fornecedores do Sebrae
(sgf.sebrae.com.br), onde os Sebrae estaduais publicam os editais de
credenciamento de consultoria e instrutoria. O Sebrae/RJ usa o SGF, e o SOMA
do Sebrae-SP manda as inscrições para ele (diagnóstico de 28/09/2026).

É um site ASP.NET WebForms: a lista (10 editais por vez) tem filtros de estado
e de situação que recarregam a página. O coletor abre a página no Playwright,
escolhe o estado (a situação já vem em "Aberto") e avança as páginas.
"""
from __future__ import annotations

import logging

from playwright.sync_api import sync_playwright

from ..filtro import normalizar
from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)

URL_PADRAO = "https://sgf.sebrae.com.br/Home/"

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
        max_paginas = int(self.fonte.get("max_paginas", 10))
        editais: dict[str, Edital] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                self.progresso.passo("Abrindo o SGF", 0, max_paginas)
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms())
                self.progresso.passo(f"Filtrando {uf}", 0, max_paginas)
                # a troca de estado recarrega a página (postback do ASP.NET)
                with page.expect_navigation(wait_until="networkidle", timeout=self.timeout_ms()):
                    page.select_option("select[id$='dropUF']", uf, timeout=self.timeout_ms())
                for pagina in range(1, max_paginas + 1):
                    self.progresso.passo(f"Página {pagina}", pagina, max_paginas)
                    grade = page.query_selector("table[id$='gvEdital']")
                    if not grade:
                        raise RuntimeError("a lista de editais do SGF não apareceu")
                    antes = len(editais)
                    for ed in linhas_para_editais(grade.evaluate(JS_LINHAS), self.nome, uf, url):
                        editais[ed.chave] = ed
                    proxima = page.locator("a[href*='ibtnNext']")
                    if len(editais) == antes or not proxima.count():
                        break
                    with page.expect_navigation(wait_until="networkidle",
                                                timeout=self.timeout_ms()):
                        proxima.first.click(timeout=self.timeout_ms())
            finally:
                browser.close()
        log.info("%s: %d editais", self.nome, len(editais))
        return list(editais.values())
