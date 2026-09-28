import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.coletores.base import Edital
from app.coletores.sistema_transparencia import (ColetorSistemaTransparencia,
                                                 documentos_por_processo,
                                                 registro_para_edital)
from app.filtro import encerrado

# campos da API vistos no diagnóstico de 28/09/2026; valores fictícios
CREDENCIAMENTO = {
    "codigoLicitacao": 380001, "idLicitacao": 3000400001, "numero": "000005607/2025",
    "titulo": "Contratação de serviços de desenvolvimento de conteúdo para Recursos Didáticos",
    "dataAbertura": "11/08/2025", "idEmpresa": 2, "nmEmpresa": "SENAI",
    "modalidade": "PSSD Credenciamento",
    "objeto": "Credenciamento de pessoas jurídicas para desenvolvimento de conteúdo",
    "statusLicitacao": "Aberto/Em Execução", "dtHomologacao": "30/11/0002",
    "dataPublicacao": "01/01/2025 11:00:00", "entidadeNacional": "SENAI",
    "entidadeRegional": "SENAI-SP", "itensLotes": [],
}
REFORMA = {
    **CREDENCIAMENTO, "codigoLicitacao": 383981, "idLicitacao": 3000474709,
    "numero": "000000271/2026", "titulo": "Execução de reforma das instalações elétricas",
    "modalidade": "PS - Disputa Fechada", "objeto": "Reforma elétrica da Escola SENAI",
    "statusLicitacao": "Encerrado/Concluído", "dataAbertura": "07/08/2026",
}

PAGINA = """<!doctype html><html><body>
<a href="/licitacoes/DocumentosSap?id=3000474709&name=ATA%20ABERTURA.pdf">ATA - ABERTURA.pdf</a>
<a href="/licitacoes/DocumentosSap?id=3000474709&name=PSDF%20271-2026.pdf">PSDF 271-2026.pdf</a>
<a href="/licitacoes/DocumentosSap?id=3000400001&name=EDITAL.pdf">EDITAL.pdf</a>
<a href="/licitacoes/DocumentosSap?id=3000400001&name=ATA.pdf">ATA - JULGAMENTO.pdf</a>
<a href="/outra">Outra página</a>
</body></html>"""


def test_registro_para_edital():
    ed = registro_para_edital(CREDENCIAMENTO, "SP", "https://x.test/lic")
    assert ed.id_externo == "3000400001"
    assert ed.titulo.startswith("Nº 5607/2025: Contratação de serviços")
    assert ed.unidade == "SENAI-SP"
    assert ed.tipo == "PSSD Credenciamento"
    assert ed.situacao == "Aberto/Em Execução · abertura em 11/08/2025"
    assert ed.url == "https://x.test/lic#processo-3000400001"
    assert ed.prazo is None and ed.data_publicacao is None
    assert registro_para_edital({**CREDENCIAMENTO, "titulo": ""}, "SP", "x") is None


def test_documentos_preferem_o_edital_a_ata():
    docs = documentos_por_processo(PAGINA, "https://transparencia.test/licitacoes/x")
    assert docs == {
        "3000474709": "https://transparencia.test/licitacoes/DocumentosSap?id=3000474709&name=PSDF%20271-2026.pdf",
        "3000400001": "https://transparencia.test/licitacoes/DocumentosSap?id=3000400001&name=EDITAL.pdf",
    }


def test_encerrado():
    assert encerrado("Encerrado/Concluído · abertura em 07/08/2026")
    assert encerrado("CANCELADO")
    assert not encerrado("Aberto/Em Execução · abertura em 11/08/2025")
    assert not encerrado("")


class Transparencia(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api":
            ano = parse_qs(url.query)["ano"][0]
            # o credenciamento aberto de 2025 não volta na lista do ano atual
            regs = [REFORMA] if ano == str(date.today().year) else [CREDENCIAMENTO, REFORMA]
            corpo, tipo = json.dumps(regs), "application/json"
        else:
            corpo, tipo = PAGINA, "text/html; charset=utf-8"
        dados = corpo.encode()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


@pytest.fixture
def transparencia():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Transparencia)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_coletor(transparencia):
    fonte = {"nome": "Transparência SENAI-SP", "url": f"{transparencia}/licitacoes/x",
             "api": f"{transparencia}/api", "departamento": "SENAI-SP", "entidade": "SENAI",
             "anos": 2}
    editais = ColetorSistemaTransparencia(fonte, {"coleta": {"timeout_segundos": 30}}).coletar()

    por_id = {e.id_externo: e for e in editais}
    assert set(por_id) == {"3000400001", "3000474709"}  # o repetido entra uma vez só
    assert por_id["3000400001"].url.endswith("name=EDITAL.pdf")
    assert por_id["3000474709"].url.endswith("name=PSDF%20271-2026.pdf")


def test_esconder_encerrados(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "editais.db")
    db.iniciar()
    for ident, situacao in (("1", "Aberto/Em Execução"), ("2", "Encerrado/Concluído")):
        db.salvar(Edital(fonte="SP", id_externo=ident, titulo=ident, url="https://x.test",
                         situacao=situacao, uf="SP"))
    assert [e["id_externo"] for e in db.listar(apenas_abertos=True)] == ["1"]
    assert len(db.listar(apenas_abertos=False)) == 2
