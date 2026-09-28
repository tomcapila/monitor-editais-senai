import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from app.coletores import sebrae_canal
from app.coletores.sebrae_canal import ColetorSebraeCanal, do_estado, registro_para_edital
from app.coletores.sebrae_one import ColetorSebraeOne, editais_para_itens
from app.coletores.sebrae_sgf import ColetorSebraeSgf

CONFIG = {"coleta": {"timeout_segundos": 30}}

# ---------- Sebrae One (MG): campos da API vistos no diagnóstico; valores fictícios

EDITAIS_ONE = [
    {"id": 71, "codigo_ano": "010/2026", "titulo": "EDUCAMPO", "status": "A",
     "data_abertura": "2026-04-22 14:25:00", "resumo": "Credenciar empresas do Educampo",
     "processos": [
         {"id": 64, "edital_id": 71, "titulo": "Abertura: Cafeicultura",
          "descricao": "Convoca empresas de consultoria em cafeicultura",
          "created_at": "2026-04-23T14:06:58.000000Z"},
         {"id": 65, "edital_id": 71, "titulo": "Abertura: Pecuária Leiteira",
          "descricao": "Convoca empresas de instrutoria em pecuária"},
     ]},
    {"id": 63, "codigo_ano": "002/2026", "titulo": "INOVAÇÃO EM TERRITÓRIOS", "status": "A",
     "data_abertura": "2026-02-06 15:40:00", "resumo": "Edital de inovação", "processos": []},
]


def test_sebrae_one_uma_linha_por_chamada():
    itens = {e.id_externo: e for e in editais_para_itens(EDITAIS_ONE, "Sebrae MG")}
    assert set(itens) == {"processo-64", "processo-65", "edital-63"}
    cafe = itens["processo-64"]
    assert cafe.titulo == "Edital 010/2026: EDUCAMPO · Abertura: Cafeicultura"
    assert cafe.objeto == "Convoca empresas de consultoria em cafeicultura"
    assert cafe.url == "https://credenciamento.sebraemg.com.br/edital/71"
    assert cafe.situacao == "Aberto" and cafe.tipo == "Credenciamento"
    assert cafe.data_publicacao == date(2026, 4, 23)
    assert itens["processo-65"].data_publicacao == date(2026, 4, 22)  # cai para o edital
    assert itens["edital-63"].titulo == "Edital 002/2026: INOVAÇÃO EM TERRITÓRIOS"
    assert itens["edital-63"].objeto == "Edital de inovação"


# ---------- servidor falso para os três sites

CANAL_REGS = [
    {"Id": 1, "Numero": "CP/001-SEBRAE-MG-2026", "Objeto": "Credenciamento de consultoria",
     "StatusDescricao": "Em Andamento", "DataPublicacao": "/Date(1788231600000)/",
     "DataCredenciamentoFim": "/Date(1790823600000)/"},
    {"Id": 2, "Numero": "PE/010-SEBRAE-RJ-2026", "Objeto": "Aquisição de notebooks",
     "StatusDescricao": "Em Andamento"},
    {"Id": 3, "Numero": "CP/002-SEBRAE-MA-2026", "Objeto": "Patrocínio de eventos",
     "StatusDescricao": "Em Andamento"},
    {"Id": 4, "Numero": "CP 05/2026", "SebraeDescricao": "SEBRAE MINAS GERAIS",
     "Objeto": "Instrutoria em gestão", "StatusDescricao": "Em Andamento"},
]

CANAL_HTML = """<!doctype html><html><body><div id="grade"></div><div id="pag"></div>
<script>
let pagina = 1;
async function carregar() {
  const r = await fetch('Licitacoes/GetLicitacoesGrid?p=' + pagina);
  const d = await r.json();
  document.getElementById('grade').textContent = d.aaData.map(x => x.Numero).join(', ');
  document.getElementById('pag').innerHTML = pagina < 2
    ? '<a href="#" onclick="pagina++; carregar(); return false">&gt;</a>' : '';
}
carregar();
</script></body></html>"""

SGF_HTML = """<!doctype html><html><body>
<select id="ctl00_cphConteudo_gvEdital_ctl01_dropUF"
        onchange="location.search = '?uf=' + this.value">
  <option>Todos</option><option>MG</option><option>RJ</option><option>SP</option>
</select>
<table id="ctl00_cphConteudo_gvEdital">
  <tr><th>UF<br>Todos</th><th>CÓDIGO</th><th>TÍTULO</th><th>STATUS</th>
      <th>DATA DA PUBLICAÇÃO</th><th>DATA DO RESULTADO</th><th></th></tr>
  {linhas}
  <tr><td colspan="7">{paginacao}</td></tr>
</table></body></html>"""


def linha_sgf(uf, codigo, titulo):
    return (f"<tr><td>{uf}</td><td>{codigo}</td><td>{titulo}</td><td>Aberto</td>"
            f"<td>15/09/2025</td><td>-</td><td><a href=\"javascript:__doPostBack('x','')\">"
            f"arquivos</a> <a href=\"/inscricao/login.aspx?Codigo={codigo}\">Inscrição</a>"
            f"</td></tr>")


class Sites(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _responder(self, corpo: str, tipo: str = "text/html; charset=utf-8"):
        dados = corpo.encode()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        if url.path == "/one/api":
            return self._responder(json.dumps({"success": True, "data": EDITAIS_ONE}),
                                   "application/json")
        if url.path == "/portalcf/Licitacoes":
            return self._responder(CANAL_HTML)
        if url.path == "/portalcf/Licitacoes/GetLicitacoesGrid":
            p = int(q["p"][0])
            regs = CANAL_REGS[:2] if p == 1 else CANAL_REGS[2:]
            return self._responder(json.dumps({"sEcho": "1", "aaData": regs}),
                                   "application/json")
        if url.path == "/sgf/Home/":
            uf, pag = q.get("uf", [""])[0], q.get("p", ["1"])[0]
            if uf != "RJ":  # sem filtro: editais de vários estados
                linhas = linha_sgf("SC", "SC20250002", "Credenciamento SC")
                paginacao = ""
            elif pag == "1":
                linhas = linha_sgf("RJ", "RJ20260001", "Consultoria e instrutoria RJ")
                paginacao = ("<a href=\"javascript:location.search='?uf=RJ&p=2';void(0)"
                             "//ibtnNext\">próxima</a>")
            else:
                linhas = linha_sgf("RJ", "RJ20250003", "Educação empreendedora RJ")
                paginacao = ""
            return self._responder(SGF_HTML.replace("{linhas}", linhas)
                                   .replace("{paginacao}", paginacao))
        self.send_error(404)


@pytest.fixture
def sites():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Sites)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_sebrae_one_pela_api(sites):
    fonte = {"nome": "Sebrae MG - credenciamento", "api": f"{sites}/one/api"}
    itens = ColetorSebraeOne(fonte, CONFIG).coletar()
    assert len(itens) == 3


# ---------- Canal do Fornecedor

def test_canal_marcas_do_estado():
    mg = ["SEBRAE-MG", "SEBRAE MINAS", "MINAS GERAIS"]
    assert do_estado(CANAL_REGS[0], mg)
    assert do_estado(CANAL_REGS[3], mg)  # pela unidade
    assert not do_estado(CANAL_REGS[1], mg)
    assert not do_estado(CANAL_REGS[2], mg)


def test_canal_registro():
    ed = registro_para_edital(CANAL_REGS[0], "Sebrae MG", "MG")
    assert ed.id_externo == "1" and ed.titulo == "CP/001-SEBRAE-MG-2026"
    assert ed.url.endswith("/Licitacoes/Detalhe?Id=1")
    assert ed.unidade == "Sebrae/MG"  # sem unidade no registro
    assert ed.situacao == "Em Andamento"
    assert ed.prazo == date(2026, 10, 1)
    assert registro_para_edital(CANAL_REGS[3], "Sebrae MG", "MG").unidade == "SEBRAE MINAS GERAIS"


def test_canal_percorre_paginas_e_le_uma_vez(sites, monkeypatch):
    monkeypatch.setattr(sebrae_canal, "_cache", {})
    url = f"{sites}/portalcf/Licitacoes"
    mg = ColetorSebraeCanal({"nome": "Sebrae MG", "uf": "MG", "url": url,
                             "marcas": ["SEBRAE-MG", "MINAS GERAIS"]}, CONFIG).coletar()
    assert sorted(e.id_externo for e in mg) == ["1", "4"]  # 4 está na página 2
    # a segunda fonte reaproveita a lista, sem abrir o site de novo
    monkeypatch.setattr(ColetorSebraeCanal, "_ler_grade", lambda *a: pytest.fail("leu de novo"))
    rj = ColetorSebraeCanal({"nome": "Sebrae RJ", "uf": "RJ", "url": url}, CONFIG).coletar()
    assert [e.id_externo for e in rj] == ["2"]


# ---------- SGF

def test_sgf_filtra_estado_e_avanca_paginas(sites):
    fonte = {"nome": "Sebrae RJ - credenciamento", "uf": "RJ", "url": f"{sites}/sgf/Home/"}
    editais = {e.id_externo: e for e in ColetorSebraeSgf(fonte, CONFIG).coletar()}
    assert set(editais) == {"RJ20260001", "RJ20250003"}
    ed = editais["RJ20260001"]
    assert ed.titulo == "RJ20260001: Consultoria e instrutoria RJ"
    assert ed.url.endswith("/inscricao/login.aspx?Codigo=RJ20260001")
    assert ed.situacao == "Aberto" and ed.unidade == "Sebrae/RJ"
    assert ed.data_publicacao == date(2025, 9, 15)
