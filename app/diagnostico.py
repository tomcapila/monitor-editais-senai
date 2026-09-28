"""
Diagnóstico do Portal de Compras FIEMG.

Pode rodar de dois jeitos:
  - pelo painel (botão "Rodar diagnóstico"), sem janela;
  - pelo terminal: python scripts/diagnostico_fiemg.py (com janela visível).

Salva em diagnostico/: pagina.html, tela.png, tabelas.json, rede.json.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

from playwright.sync_api import sync_playwright

from .config import BASE_DIR, carregar_config
from .progresso import Progresso, TempoEsgotado

URL_PADRAO = "https://compras.fiemg.com.br/portal/Mural.aspx?nNmTela=E"
SAIDA = BASE_DIR / "diagnostico"

JS = """
els => els.map((t, i) => ({
  indice: i,
  id: t.id,
  headers: [...t.querySelectorAll('th')].map(h => h.innerText.trim()),
  linhas: [...t.querySelectorAll('tbody tr')].slice(0, 3)
           .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
  total_linhas: t.querySelectorAll('tbody tr').length,
}))
"""

_lock = threading.Lock()
estado = {"erro": None}
progresso = Progresso()

FASES = ["Abrindo o navegador", "Carregando o portal", "Aguardando as tabelas (AJAX)",
         "Salvando HTML e captura da tela", "Lendo as tabelas", "Gravando os arquivos"]


def rodar(url: str = URL_PADRAO, visivel: bool = False, pausa=None,
          limite_segundos: float | None = None) -> dict:
    """Executa o diagnóstico e devolve o resumo. 'pausa' é chamada antes de fechar."""
    if not _lock.acquire(blocking=False):
        return {"status": "ja_rodando"}
    if limite_segundos is None:
        limite_segundos = carregar_config().get("diagnostico", {}).get("tempo_limite_segundos", 180)
    progresso.iniciar(limite_segundos, len(FASES))
    estado["erro"] = None
    SAIDA.mkdir(exist_ok=True)
    chamadas = []
    try:
        with sync_playwright() as p:
            progresso.fase(FASES[0], 0)
            browser = p.chromium.launch(headless=not visivel)
            page = browser.new_page(locale="pt-BR")

            def registrar(resp):
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                item = {"url": resp.url, "metodo": resp.request.method,
                        "status": resp.status,
                        "tipo": resp.headers.get("content-type", ""),
                        "post": resp.request.post_data}
                try:
                    item["amostra"] = resp.text()[:800]
                except Exception:
                    pass
                chamadas.append(item)
                try:
                    progresso.passo(f"{len(chamadas)} chamadas AJAX registradas")
                except TempoEsgotado:
                    pass  # dentro de um evento do Playwright; o fluxo principal trata

            page.on("response", registrar)
            progresso.fase(FASES[1], 1)
            page.goto(url, wait_until="networkidle", timeout=progresso.restante_ms(90000))
            progresso.fase(FASES[2], 2)
            page.wait_for_timeout(progresso.restante_ms(4000))

            progresso.fase(FASES[3], 3)
            (SAIDA / "pagina.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(SAIDA / "tela.png"), full_page=True,
                            timeout=progresso.restante_ms(30000))
            progresso.fase(FASES[4], 4)
            tabelas = page.eval_on_selector_all("table", JS)
            if pausa:
                progresso.sem_limite()  # o tempo com o usuário navegando não conta
                pausa()
            browser.close()

        progresso.fase(FASES[5], 5)
        resumo = {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "url": url,
            "tabelas": tabelas,
            "rede": chamadas,
        }
        (SAIDA / "tabelas.json").write_text(
            json.dumps(tabelas, ensure_ascii=False, indent=2), encoding="utf-8")
        (SAIDA / "rede.json").write_text(
            json.dumps(chamadas, ensure_ascii=False, indent=2), encoding="utf-8")
        (SAIDA / "resumo.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", **resumo}
    except Exception as e:
        erro = str(e)
        status = "tempo_esgotado" if isinstance(e, TempoEsgotado) else "erro"
        try:
            progresso.verificar()  # timeout do Playwright pode ter sido o limite total
        except TempoEsgotado as te:
            erro, status = str(te), "tempo_esgotado"
        estado["erro"] = erro
        return {"status": status, "erro": erro}
    finally:
        progresso.finalizar()
        _lock.release()


def ultimo_resultado() -> dict | None:
    arq = SAIDA / "resumo.json"
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))
