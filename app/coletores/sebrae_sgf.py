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

# A grade de editais: no site real a <table> vem sem id (diagnóstico de
# 28/09/2026), então é achada pelo próprio cabeçalho ("CÓDIGO"). O layout usa
# tabelas por fora e a paginação do ASP.NET é outra tabela por dentro, por isso
# só contam as células que pertencem à própria grade.
JS_GRADE = """
() => [...document.querySelectorAll('table')].find(t =>
  [...t.querySelectorAll('th')].some(th => th.closest('table') === t
    && /^C[ÓO]DIGO/i.test((th.innerText || '').trim()))) || null
"""
JS_TEXTO_GRADE = f"() => {{ const t = ({JS_GRADE})(); return t ? t.innerText : null; }}"

# Linhas da grade: células visíveis e links que não são postback
JS_LINHAS = f"""
() => {{
  const tab = ({JS_GRADE})();
  if (!tab) return null;
  return [...tab.querySelectorAll('tr')].filter(tr => tr.closest('table') === tab).map(tr => ({{
    th: [...tr.querySelectorAll('th')].map(c => (c.innerText || '').split('\\n')[0].trim()),
    td: [...tr.querySelectorAll('td')].map(c => (c.innerText || '').trim()),
    links: [...tr.querySelectorAll('a[href]')].map(a => a.href)
             .filter(h => h && !h.startsWith('javascript')),
  }}));
}}
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
                try:  # a lista pode chegar depois do carregamento da página
                    page.wait_for_function(JS_TEXTO_GRADE, timeout=30000)
                except Exception:
                    pass  # o erro abaixo mostra o texto da página
                for pagina in range(1, max_paginas + 1):
                    self.progresso.passo(f"Página {pagina}", pagina, max_paginas)
                    atuais = page.evaluate(JS_LINHAS)
                    if atuais is None:
                        texto = " ".join(page.inner_text("body").split())[:300]
                        raise RuntimeError(f"a lista de editais do SGF não apareceu: {texto}")
                    linhas += atuais
                    proxima = page.locator("a[href*='ibtnNext']")
                    if not proxima.count():
                        break
                    antes = page.evaluate(JS_TEXTO_GRADE)
                    proxima.first.click(timeout=self.timeout_ms())
                    try:  # postback: completo ou parcial (UpdatePanel); espera a grade mudar
                        page.wait_for_function(
                            f"antes => {{ const t = ({JS_TEXTO_GRADE})(); return t && t !== antes; }}",
                            arg=antes, timeout=20000)
                    except Exception:
                        log.info("SGF: a página %d não mudou; fim da lista", pagina + 1)
                        break
            finally:
                browser.close()
        return linhas
