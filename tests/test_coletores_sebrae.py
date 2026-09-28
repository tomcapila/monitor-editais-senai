import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from app.coletores import sebrae_canal, sebrae_sgf
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
    # o edital sempre entra, e cada chamada também
    assert set(itens) == {"edital-71", "processo-64", "processo-65", "edital-63"}
    assert itens["edital-71"].titulo == "Edital 010/2026: EDUCAMPO"
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
            # como o site real: a lista inteira de uma vez (o ">" não pede de novo)
            regs = CANAL_REGS if self.server.canal_inteiro else (
                CANAL_REGS[:2] if p == 1 else CANAL_REGS[2:])
            return self._responder(json.dumps({"sEcho": "1", "aaData": regs}),
                                   "application/json")
        if url.path == "/sgf/Home/":
            # lista nacional de editais abertos, 2 páginas
            if q.get("p", ["1"])[0] == "1":
                linhas = (linha_sgf("SC", "SC20250002", "Credenciamento SC")
                          + linha_sgf("RJ", "RJ20260001", "Consultoria e instrutoria RJ"))
                paginacao = ("<a href=\"javascript:location.search='?p=2';void(0)"
                             "//ibtnNext\">próxima</a>")
            else:
                linhas = (linha_sgf("RJ", "RJ20250003", "Educação empreendedora RJ")
                          + linha_sgf("SP", "SP20260001", "SOMA Sebrae SP"))
                paginacao = ""
            return self._responder(SGF_HTML.replace("{linhas}", linhas)
                                   .replace("{paginacao}", paginacao))
        self.send_error(404)


@pytest.fixture
def sites():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Sites)
    srv.canal_inteiro = False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", srv
    srv.shutdown()


@pytest.fixture
def base(sites):
    return sites[0]


def test_sebrae_one_pela_api(base):
    fonte = {"nome": "Sebrae MG - credenciamento", "api": f"{base}/one/api"}
    itens = ColetorSebraeOne(fonte, CONFIG).coletar()
    assert len(itens) == 4


# ---------- Canal do Fornecedor

def test_canal_marcas_do_estado():
    mg = ["SEBRAE-MG", "SEBRAE MINAS", "MINAS GERAIS"]
    assert do_estado(CANAL_REGS[0], "MG", mg)
    assert do_estado(CANAL_REGS[3], "MG", mg)  # pela unidade
    assert not do_estado(CANAL_REGS[1], "MG", mg)
    assert not do_estado(CANAL_REGS[2], "MG", mg)
    # com a UF da unidade no registro, ela decide (o Sebrae Nacional cita o RJ no objeto)
    nacional = {"Id": 9, "Numero": "PE/001-SEBRAE-NA-2026", "Objeto": "Evento no Rio de Janeiro",
                "ZSebrae": {"Descricao": "SEBRAE NACIONAL", "Uf": "DF"}}
    assert not do_estado(nacional, "RJ", ["RIO DE JANEIRO"])
    assert do_estado({**nacional, "ZSebrae": {"Uf": "rj"}}, "RJ", [])


def test_canal_registro():
    ed = registro_para_edital(CANAL_REGS[0], "Sebrae MG", "MG")
    assert ed.id_externo == "1" and ed.titulo == "CP/001-SEBRAE-MG-2026"
    assert ed.url.endswith("/Licitacoes/Detalhe?Id=1")
    assert ed.unidade == "Sebrae/MG"  # sem unidade no registro
    assert ed.situacao == "Em Andamento"
    assert ed.prazo == date(2026, 10, 1)
    assert registro_para_edital(CANAL_REGS[3], "Sebrae MG", "MG").unidade == "SEBRAE MINAS GERAIS"


@pytest.mark.parametrize("inteiro", [True, False])
def test_canal_le_a_lista_uma_vez(sites, monkeypatch, inteiro):
    base, srv = sites
    srv.canal_inteiro = inteiro  # lista inteira de uma vez, ou uma página por clique
    monkeypatch.setattr(sebrae_canal, "_cache", {})
    url = f"{base}/portalcf/Licitacoes"
    mg = ColetorSebraeCanal({"nome": "Sebrae MG", "uf": "MG", "url": url,
                             "marcas": ["SEBRAE-MG", "MINAS GERAIS"]}, CONFIG).coletar()
    assert sorted(e.id_externo for e in mg) == ["1", "4"]
    # a segunda fonte reaproveita a lista, sem abrir o site de novo
    monkeypatch.setattr(ColetorSebraeCanal, "_ler_grade", lambda *a: pytest.fail("leu de novo"))
    rj = ColetorSebraeCanal({"nome": "Sebrae RJ", "uf": "RJ", "url": url}, CONFIG).coletar()
    assert [e.id_externo for e in rj] == ["2"]


# ---------- SGF

def test_sgf_percorre_lista_e_separa_estados(base, monkeypatch):
    monkeypatch.setattr(sebrae_sgf, "_cache", {})
    fonte = {"nome": "Sebrae RJ - credenciamento", "uf": "RJ", "url": f"{base}/sgf/Home/"}
    editais = {e.id_externo: e for e in ColetorSebraeSgf(fonte, CONFIG).coletar()}
    assert set(editais) == {"RJ20260001", "RJ20250003"}
    ed = editais["RJ20260001"]
    assert ed.titulo == "RJ20260001: Consultoria e instrutoria RJ"
    assert ed.url.endswith("/inscricao/login.aspx?Codigo=RJ20260001")
    assert ed.situacao == "Aberto" and ed.unidade == "Sebrae/RJ"
    assert ed.data_publicacao == date(2025, 9, 15)
    # SP reaproveita a lista já lida
    monkeypatch.setattr(ColetorSebraeSgf, "_ler_lista", lambda *a: pytest.fail("leu de novo"))
    sp = ColetorSebraeSgf({**fonte, "nome": "Sebrae SP", "uf": "SP"}, CONFIG).coletar()
    assert [e.id_externo for e in sp] == ["SP20260001"]
