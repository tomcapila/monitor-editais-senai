"""
Coletor do Portal de Compras da FIEMG (plataforma Paradigma).

O portal carrega as tabelas via JavaScript, por isso usamos Playwright
(navegador real, sem janela). A estratégia é genérica: renderiza a página,
lê todas as tabelas e mapeia as colunas pelo texto do cabeçalho.

ATENÇÃO: este coletor não foi testado contra o site real. Rode
scripts/diagnostico_fiemg.py primeiro e ajuste MAPA_COLUNAS e 'expandir'
no config.yaml conforme o que aparecer.
"""
from __future__ import annotations

import logging
import unicodedata

from playwright.sync_api import sync_playwright

from ..progresso import TempoEsgotado
from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


# Cabeçalho normalizado -> campo do Edital. A primeira coluna não vazia vence.
MAPA_COLUNAS = {
    "id_externo": ["codigo", "processo", "numero", "edital", "rfi"],
    "titulo": ["chamamento publico", "titulo", "edital"],
    "objeto": ["objeto"],
    "unidade": ["unidade compradora"],
    "tipo": ["modalidade", "tipo", "linha de fornecimento"],
    "situacao": ["situacao"],
    "prazo": ["encerramento das inscricoes", "encerra em", "data/hora final"],
    "data_publicacao": ["inicio das inscricoes", "data/hora inicial"],
}

# Tabelas com estes cabeçalhos listam empresas já credenciadas, não editais.
CABECALHOS_IGNORAR = {"empresa", "aprovacao"}

# Valores de célula que o portal usa como "vazio".
VALORES_VAZIOS = {"nao informado"}

# O portal usa a mesma tabela para várias visões e esconde colunas com
# display:none (ex.: #tbEditais tem 21 <th>, mas só 8 visíveis e 8 <td> por linha).
# Por isso só contamos cabeçalhos e células visíveis.
JS_TABELAS = """
els => els.map(t => {
  const visivel = el => getComputedStyle(el).display !== 'none';
  let headers = [...t.querySelectorAll('thead th')].filter(visivel).map(h => h.innerText.trim());
  let linhas = [...t.querySelectorAll('tbody tr')];
  if (!headers.length) {
    const primeira = t.querySelector('tr');
    if (primeira) headers = [...primeira.querySelectorAll('th')].filter(visivel).map(h => h.innerText.trim());
  }
  return {
    headers,
    rows: linhas.map(tr => ({
      cells: [...tr.querySelectorAll('td')].filter(visivel).map(td => td.innerText.trim()),
      links: [...tr.querySelectorAll('a[href]')]
               .map(a => a.href)
               .filter(h => h && !h.startsWith('javascript')),
    })),
  };
})
"""


class ColetorFiemgParadigma(Coletor):
    def coletar(self) -> list[Edital]:
        resultados: dict[str, Edital] = {}
        expandir = self.fonte.get("expandir", [])
        total = 1 + len(expandir)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                # 1) página inicial do mural
                self.progresso.passo("Abrindo o mural", 0, total)
                self._abrir(page)
                for ed in self._extrair(page):
                    resultados[ed.chave] = ed

                # 2) listas completas ("Ver todos...")
                for i, texto in enumerate(expandir, start=1):
                    self.progresso.passo(f"Expandindo '{texto}'", i, total)
                    try:
                        self._abrir(page)
                        # são <button onclick="Expandir...()">; o mesmo texto aparece
                        # também fora do botão, por isso buscamos pelo papel
                        link = page.get_by_role("button", name=texto).first
                        link.click(timeout=self.progresso.restante_ms(5000))
                        page.wait_for_load_state("networkidle", timeout=self.timeout_ms())
                        page.wait_for_timeout(1500)
                        for ed in self._extrair(page):
                            resultados[ed.chave] = ed
                    except TempoEsgotado:
                        raise
                    except Exception as e:  # link pode não existir ou mudar
                        log.warning("Não consegui expandir '%s': %s", texto, e)
            finally:
                browser.close()
        return list(resultados.values())

    def _abrir(self, page):
        page.goto(self.url, wait_until="networkidle", timeout=self.timeout_ms())
        # as tabelas chegam por AJAX depois do carregamento
        page.wait_for_timeout(2000)

    def _extrair(self, page) -> list[Edital]:
        tabelas = page.eval_on_selector_all("table", JS_TABELAS)
        editais = []
        for tab in tabelas:
            headers = [_norm(h) for h in tab["headers"]]
            if not headers or CABECALHOS_IGNORAR.issubset(set(headers)):
                continue
            if not any(h in ("objeto", "chamamento publico") for h in headers):
                continue
            for row in tab["rows"]:
                ed = self._linha_para_edital(headers, row)
                if ed:
                    editais.append(ed)
        return editais

    def _linha_para_edital(self, headers: list[str], row: dict) -> Edital | None:
        cells = row["cells"]
        if len(cells) < 2:
            return None

        def campo(nome: str) -> str:
            for alvo in MAPA_COLUNAS[nome]:
                for i, h in enumerate(headers):
                    if (h == alvo and i < len(cells) and cells[i]
                            and _norm(cells[i]) not in VALORES_VAZIOS):
                        return cells[i]
            return ""

        objeto = campo("objeto")
        titulo = campo("titulo") or objeto[:140]
        if not titulo:
            return None

        return Edital(
            fonte=self.nome,
            titulo=titulo,
            objeto=objeto,
            url=(row["links"][0] if row["links"] else self.url),
            id_externo=campo("id_externo"),
            unidade=campo("unidade"),
            tipo=campo("tipo"),
            situacao=campo("situacao"),
            prazo=parse_data(campo("prazo")),
            data_publicacao=parse_data(campo("data_publicacao")),
        )
