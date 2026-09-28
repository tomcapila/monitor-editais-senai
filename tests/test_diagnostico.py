import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import diagnostico

# Imita um portal Paradigma: o mural em /portal/Mural.aspx e o serviço JSON
# em /portal/WebService/Servicos.asmx (o fetch do coletor usa caminho relativo).
MURAL = """<!doctype html><html><meta charset="utf-8"><title>PORTAL DE COMPRAS TESTE</title>
<body>
<table id="tbEditais"><thead><tr><th>Número</th><th>Objeto</th></tr></thead>
<tbody><tr><td>CRED 1</td><td>Credenciamento de consultores</td></tr></tbody></table>
<a href="/arquivos/edital-cred-1.pdf">Edital de credenciamento 1</a>
<a href="/contato">Fale conosco</a>
</body></html>"""

REGISTRO = {"nCdProcesso": 777, "nCdModulo": 53, "sNrEdital": "CRED 2026000001",
            "sDsObjeto": "Credenciamento de pessoas jurídicas para instrutoria",
            "sNmEmpresa": "SENAI/RJ - SEDE", "sNmModalidade": "Credenciamento",
            "tDtInicial": "01/09/2026 08:00:00", "tDtFinal": "30/10/2026 17:00:00"}


class Portal(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _responder(self, corpo: str, tipo: str):
        dados = corpo.encode()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        self._responder(MURAL, "text/html; charset=utf-8")

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        # o mural tem um processo; as listas simplificadas vêm vazias
        regs = [REGISTRO] if self.path.endswith("/PesquisarProcessos") else []
        self._responder(json.dumps({"d": regs}), "application/json; charset=utf-8")


@pytest.fixture
def portal():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_diagnostico_de_portal_paradigma(portal, tmp_path):
    r = diagnostico.rodar(f"{portal}/portal/Mural.aspx?nNmTela=ME",
                          limite_segundos=60, saida=tmp_path)

    assert r["status"] == "ok", r.get("erro")
    assert r["titulo"] == "PORTAL DE COMPRAS TESTE"
    assert r["tabelas"][0]["headers"] == ["Número", "Objeto"]
    assert {"texto": "Edital de credenciamento 1",
            "href": f"{portal}/arquivos/edital-cred-1.pdf"} in r["links"]

    mural = r["paradigma"]["mural"]
    assert mural["registros"] == 1
    assert "sNmEmpresa" in mural["campos"]
    ed = mural["como_edital"][0]
    assert ed["unidade"] == "SENAI/RJ - SEDE"
    assert ed["prazo"] == "2026-10-30"
    assert r["paradigma"]["rfis"]["registros"] == 0

    for arq in ("pagina.html", "tela.png", "tabelas.json", "links.json", "rede.json",
                "resumo.json", "paradigma.json"):
        assert (tmp_path / arq).exists(), arq

    texto = diagnostico.relatorio(r)
    assert "Edital de credenciamento 1" in texto
    assert "Fale conosco" not in texto  # só os links com cara de edital
    assert "mural: 1 registros" in texto
    assert "SENAI/RJ - SEDE" in texto


def test_diagnostico_sem_mural_nao_testa_paradigma(portal, tmp_path):
    r = diagnostico.rodar(f"{portal}/licitacoes", limite_segundos=60, saida=tmp_path)

    assert r["status"] == "ok", r.get("erro")
    assert r["paradigma"] is None
    assert not (tmp_path / "paradigma.json").exists()


def test_relatorio_de_falha():
    texto = diagnostico.relatorio({"status": "erro", "url": "https://x.test", "erro": "recusou"})
    assert "https://x.test" in texto
    assert "FALHOU (erro): recusou" in texto
