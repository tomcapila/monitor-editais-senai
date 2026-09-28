"""
Diagnóstico de um portal de compras (FIEMG por padrão, mas serve para qualquer URL).

Pode rodar de três jeitos:
  - pelo painel (botão "Rodar diagnóstico"), sem janela, no portal da FIEMG;
  - pelo terminal: python scripts/diagnostico_fiemg.py (com janela visível);
  - para várias URLs: python scripts/diagnostico_portais.py URL [URL ...]
    (é o que o workflow .github/workflows/diagnostico.yml usa).

Salva na pasta de saída: pagina.html, tela.png, tabelas.json, links.json,
rede.json, resumo.json e, em portais Paradigma (Mural.aspx), paradigma.json.
"""
from __future__ import annotations

import copy
import json
import threading
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from .coletores.base import USER_AGENT
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

# Links e iframes: portais que não usam <table> costumam listar editais como links
JS_LINKS = """
els => els.slice(0, 400).map(a => ({
  texto: (a.innerText || a.title || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
  href: a.href,
}))
"""
JS_IFRAMES = "els => els.map(f => f.src)"
# Formulários: filtros de ano, paginação e busca costumam ser um <form> com GET
JS_FORMS = """
els => els.map(f => ({
  action: f.action, metodo: (f.method || 'get').toUpperCase(),
  campos: [...f.elements].filter(e => e.name).slice(0, 30).map(e => ({
    nome: e.name, tipo: e.type, valor: e.value,
    opcoes: e.options ? [...e.options].slice(0, 20).map(o => o.value + '=' + o.text.trim()) : undefined,
  })),
}))
"""

# Consulta de teste ao serviço Paradigma: poucos registros por lista
REGISTROS_TESTE = 10

_lock = threading.Lock()
estado = {"erro": None}
progresso = Progresso()

FASES = ["Abrindo o navegador", "Carregando o portal", "Aguardando as tabelas (AJAX)",
         "Salvando HTML e captura da tela", "Lendo as tabelas", "Gravando os arquivos"]


def _carregar(page, url: str) -> str | None:
    """Abre a página esperando a rede acalmar. Se ela nunca acalma (anúncios,
    chat, métricas), segue com o que carregou e devolve um aviso."""
    try:
        page.goto(url, wait_until="networkidle", timeout=progresso.restante_ms(90000))
        return None
    except ErroPlaywright as e:
        progresso.verificar()
        if "Timeout" not in str(e) or page.url in ("", "about:blank"):
            raise
        return "a página não parou de fazer chamadas; o diagnóstico usou o que já tinha carregado"


def testar_paradigma(page) -> dict:
    """Faz as mesmas chamadas do coletor paradigma_api de dentro da página e mostra
    o que ele montaria. Serve para saber se outro portal Paradigma (ex.: Firjan)
    responde igual ao da FIEMG."""
    from .coletores.paradigma_api import JS_CONSULTA, LISTAS, mural, registro_para_edital

    base = mural(page.url)
    resultado = {}
    for nome, lista in LISTAS.items():
        dto = copy.deepcopy(lista["dto"])
        dto["dtoPaginacao"] = {"nPaginaDe": 1, "nPaginaAte": REGISTROS_TESTE}
        timeout = progresso.restante_ms(30000)
        try:
            page.set_default_timeout(timeout + 5000)
            regs = page.evaluate(JS_CONSULTA, {"metodo": lista["metodo"], "dto": dto,
                                               "timeoutMs": timeout})
        except ErroPlaywright as e:
            progresso.verificar()
            resultado[nome] = {"erro": str(e).splitlines()[0][:300]}
            continue
        editais = []
        for reg in regs[:5]:
            try:
                ed = registro_para_edital(reg, nome, "teste", base, apelido_na_unidade=True)
            except Exception as e:
                editais.append({"erro": str(e)[:200]})
                continue
            if ed:
                editais.append({"titulo": ed.titulo, "objeto": ed.objeto[:200],
                                "unidade": ed.unidade, "tipo": ed.tipo,
                                "situacao": ed.situacao, "url": ed.url,
                                "publicacao": str(ed.data_publicacao or ""),
                                "prazo": str(ed.prazo or "")})
        resultado[nome] = {
            "registros": len(regs),
            "campos": sorted(regs[0]) if regs else [],
            "amostra": regs[:2],
            "como_edital": editais,
        }
    return resultado


def rodar(url: str = URL_PADRAO, visivel: bool = False, pausa=None,
          limite_segundos: float | None = None, saida: Path | None = None,
          amostra_max: int = 800) -> dict:
    """Executa o diagnóstico e devolve o resumo. 'pausa' é chamada antes de fechar.

    'saida' é a pasta dos arquivos (padrão: diagnostico/, a que o painel lê);
    'amostra_max' é quantos caracteres de cada resposta AJAX guardar.
    """
    if not _lock.acquire(blocking=False):
        return {"status": "ja_rodando"}
    if limite_segundos is None:
        limite_segundos = carregar_config().get("diagnostico", {}).get("tempo_limite_segundos", 180)
    saida = Path(saida or SAIDA)
    progresso.iniciar(limite_segundos, len(FASES))
    estado["erro"] = None
    saida.mkdir(parents=True, exist_ok=True)
    chamadas, avisos = [], []
    try:
        with sync_playwright() as p:
            progresso.fase(FASES[0], 0)
            browser = p.chromium.launch(headless=not visivel)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)

            def registrar(resp):
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                item = {"url": resp.url, "metodo": resp.request.method,
                        "status": resp.status,
                        "tipo": resp.headers.get("content-type", ""),
                        "post": resp.request.post_data}
                try:
                    item["amostra"] = resp.text()[:amostra_max]
                except Exception:
                    pass
                chamadas.append(item)
                try:
                    progresso.passo(f"{len(chamadas)} chamadas AJAX registradas")
                except TempoEsgotado:
                    pass  # dentro de um evento do Playwright; o fluxo principal trata

            page.on("response", registrar)
            progresso.fase(FASES[1], 1)
            aviso = _carregar(page, url)
            if aviso:
                avisos.append(aviso)
            progresso.fase(FASES[2], 2)
            page.wait_for_timeout(progresso.restante_ms(4000))

            progresso.fase(FASES[3], 3)
            (saida / "pagina.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(saida / "tela.png"), full_page=True,
                            timeout=progresso.restante_ms(30000))
            progresso.fase(FASES[4], 4)
            tabelas = page.eval_on_selector_all("table", JS)
            links = page.eval_on_selector_all("a[href]", JS_LINKS)
            iframes = page.eval_on_selector_all("iframe", JS_IFRAMES)
            forms = page.eval_on_selector_all("form", JS_FORMS)
            titulo, url_final = page.title(), page.url
            paradigma = testar_paradigma(page) if "mural.aspx" in url_final.lower() else None
            if pausa:
                progresso.sem_limite()  # o tempo com o usuário navegando não conta
                pausa()
            browser.close()

        progresso.fase(FASES[5], 5)
        resumo = {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "url": url,
            "url_final": url_final,
            "titulo": titulo,
            "avisos": avisos,
            "tabelas": tabelas,
            "links": links,
            "iframes": iframes,
            "forms": forms,
            "rede": chamadas,
            "paradigma": paradigma,
        }
        arquivos = {"tabelas": tabelas, "links": links, "rede": chamadas, "resumo": resumo}
        if paradigma is not None:
            arquivos["paradigma"] = paradigma
        for nome, conteudo in arquivos.items():
            (saida / f"{nome}.json").write_text(
                json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", **resumo}
    except Exception as e:
        erro = str(e)
        status = "tempo_esgotado" if isinstance(e, TempoEsgotado) else "erro"
        try:
            progresso.verificar()  # timeout do Playwright pode ter sido o limite total
        except TempoEsgotado as te:
            erro, status = str(te), "tempo_esgotado"
        estado["erro"] = erro
        return {"status": status, "url": url, "erro": erro}
    finally:
        progresso.finalizar()
        _lock.release()


# Palavras que destacam, entre os links da página, os que parecem editais
PISTAS = ("edital", "editais", "credenciamento", "chamamento", "licita", "processo",
          "consultor", "instrutor", "fornecedor", "compras", ".pdf")


def relatorio(r: dict, max_texto: int = 1500, todos_links: bool = False) -> str:
    """Resumo legível de um diagnóstico, para o terminal e o log do GitHub Actions."""
    linhas = [f"=== {r.get('url')}"]
    if r.get("status") != "ok":
        linhas.append(f"FALHOU ({r.get('status')}): {r.get('erro')}")
        return "\n".join(linhas)
    linhas.append(f"Título: {r['titulo']!r}")
    linhas.append(f"Endereço final: {r['url_final']}")
    linhas += [f"Aviso: {a}" for a in r["avisos"]]
    if r["iframes"]:
        linhas.append(f"Iframes: {r['iframes']}")

    linhas.append(f"\n-- {len(r['tabelas'])} tabelas")
    for t in r["tabelas"]:
        linhas.append(f"#{t['indice']} id={t['id']!r} ({t['total_linhas']} linhas) "
                      f"cabeçalhos={t['headers'][:10]}")
        linhas += [f"    {ln[:8]}" for ln in t["linhas"][:2]]

    pistas = [a for a in r["links"] if todos_links
              or any(p in f"{a['texto']} {a['href']}".lower() for p in PISTAS)]
    linhas.append(f"\n-- {len(r['links'])} links, {len(pistas)} com cara de edital")
    linhas += [f"  {a['texto']!r} -> {a['href']}" for a in pistas[:60 + 340 * todos_links]]

    for fm in r.get("forms") or []:
        linhas.append(f"\n-- Formulário {fm['metodo']} {fm['action']}")
        for c in fm["campos"]:
            opcoes = f" opções={c['opcoes']}" if c.get("opcoes") else ""
            linhas.append(f"  {c['nome']} ({c['tipo']}) = {c['valor']!r}{opcoes}"[:max_texto])

    linhas.append(f"\n-- {len(r['rede'])} chamadas AJAX")
    for c in r["rede"]:
        linhas.append(f"  {c['metodo']} {c['status']} {c['url'][:200]} [{c['tipo'][:40]}]")
        if c.get("post"):
            linhas.append(f"    envio: {c['post'][:max_texto]}")
        if c.get("amostra") and "json" in c["tipo"]:
            linhas.append(f"    resposta: {c['amostra'][:max_texto]}")

    if r.get("paradigma") is not None:
        linhas.append("\n-- Teste do serviço Paradigma (mesmas chamadas do coletor paradigma_api)")
        for nome, res in r["paradigma"].items():
            if "erro" in res:
                linhas.append(f"  {nome}: ERRO {res['erro']}")
                continue
            linhas.append(f"  {nome}: {res['registros']} registros; campos={res['campos']}")
            for ed in res["como_edital"]:
                linhas.append(f"    {json.dumps(ed, ensure_ascii=False)[:max_texto]}")
    return "\n".join(linhas)


def ultimo_resultado() -> dict | None:
    arq = SAIDA / "resumo.json"
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))
