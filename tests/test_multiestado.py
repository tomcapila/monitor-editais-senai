import sqlite3

from app import alertas, coleta, db
from app.coleta import executar_coleta
from app.coletores.base import Edital


def test_fonte_nova_nao_dispara_alerta_em_massa(config_demo, monkeypatch):
    enviados = []
    monkeypatch.setattr(alertas, "enviar", lambda eds, cfg: enviados.extend(eds) or True)

    executar_coleta()  # carga inicial de MG
    assert enviados == []

    # um estado novo entra com o banco já cheio de editais de MG
    demo_mg = next(f for f in config_demo["fontes"] if f["tipo"] == "demo")
    config_demo["fontes"].append({**demo_mg, "nome": "Exemplo RJ", "uf": "RJ"})
    r = executar_coleta()
    assert r["novos"] == 3
    assert enviados == []  # a primeira coleta do RJ também é carga inicial

    todos = db.listar(apenas_relevantes=False, apenas_abertos=False)
    assert {e["uf"] for e in todos if e["fonte"] == "Exemplo RJ"} == {"RJ"}
    assert all(e["da_carga"] for e in todos)
    assert db.resumo()["pos_carga"] == 0

    # dali em diante, o que for novo no RJ alerta normalmente
    novo = Edital(fonte="Exemplo RJ", id_externo="rj-9", url="https://example.com/rj-9",
                  titulo="Credenciamento de consultores", unidade="SENAI/RJ")
    original = coleta.criar_coletor

    def coletor(fonte, cfg, prog=None):
        c = original(fonte, cfg, prog)
        if fonte["nome"] == "Exemplo RJ":
            antigo = c.coletar
            c.coletar = lambda: antigo() + [novo]
        return c

    monkeypatch.setattr(coleta, "criar_coletor", coletor)
    r = executar_coleta()
    assert r["novos"] == 1
    assert [(e.id_externo, e.uf) for e in enviados] == [("rj-9", "RJ")]
    assert db.resumo()["pos_carga"] == 1


def test_migra_banco_antigo(tmp_path, monkeypatch):
    """Banco criado antes do suporte a vários estados: tudo vira MG e a carga
    inicial antiga (a primeira coleta que salvou algo) é preservada."""
    caminho = tmp_path / "editais.db"
    monkeypatch.setattr(db, "DB_PATH", caminho)
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE editais (
            chave TEXT PRIMARY KEY,
            fonte TEXT, id_externo TEXT, titulo TEXT, objeto TEXT, unidade TEXT,
            url TEXT, situacao TEXT, tipo TEXT,
            data_publicacao TEXT, prazo TEXT,
            relevancia INTEGER, relevante INTEGER, do_senai INTEGER,
            trecho_pdf TEXT,
            primeiro_visto TEXT, ultimo_visto TEXT,
            notificado INTEGER DEFAULT 0
        );
        CREATE TABLE execucoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inicio TEXT, fim TEXT, encontrados INTEGER, novos INTEGER, erros TEXT
        );
        INSERT INTO execucoes (inicio, fim, encontrados, novos) VALUES
            ('2026-09-27T10:00:00', '2026-09-27T10:05:00', 2, 2),
            ('2026-09-27T22:00:00', '2026-09-27T22:05:00', 3, 1);
        INSERT INTO editais (chave, fonte, titulo, primeiro_visto, relevante) VALUES
            ('a', 'Portal de Compras FIEMG', 'antigo 1', '2026-09-27T10:03:00', 1),
            ('b', 'Portal de Compras FIEMG', 'antigo 2', '2026-09-27T10:04:00', 1),
            ('c', 'Portal de Compras FIEMG', 'chegou depois', '2026-09-27T22:02:00', 1);
    """)
    con.close()

    db.iniciar()
    db.iniciar()  # rodar de novo não pode quebrar nem refazer a migração

    eds = {e["chave"]: e for e in db.listar(apenas_relevantes=False, apenas_abertos=False)}
    assert {e["uf"] for e in eds.values()} == {"MG"}
    assert (eds["a"]["da_carga"], eds["b"]["da_carga"], eds["c"]["da_carga"]) == (1, 1, 0)
    assert db.resumo()["pos_carga"] == 1
    assert not db.fonte_nova("Portal de Compras FIEMG")
    assert db.fonte_nova("Portal de Compras Firjan")


def test_alerta_mostra_o_estado():
    ed = Edital(fonte="Portal", titulo="Credenciamento", url="https://x.test",
                unidade="SENAI/RJ - SEDE", uf="RJ")
    assert "RJ | SENAI/RJ - SEDE | prazo não identificado" in alertas._resumo([ed])


def test_filtro_por_estado(config_demo):
    from fastapi.testclient import TestClient

    from app.main import app

    demo_mg = next(f for f in config_demo["fontes"] if f["tipo"] == "demo")
    config_demo["fontes"].append({**demo_mg, "nome": "Exemplo RJ", "uf": "RJ"})
    executar_coleta()
    with TestClient(app) as cliente:
        todos = {"relevantes": "false", "abertos": "false"}
        assert len(cliente.get("/api/editais", params=todos).json()) == 6
        rj = cliente.get("/api/editais", params={**todos, "uf": "RJ"}).json()
        assert len(rj) == 3 and {e["uf"] for e in rj} == {"RJ"}
        assert cliente.get("/api/resumo").json()["ufs"] == {"MG": 3, "RJ": 3}
        # os números dos botões acompanham os outros filtros
        assert cliente.get("/api/estados", params=todos).json() == {"MG": 3, "RJ": 3}
        assert cliente.get("/api/estados").json() == {"MG": 2, "RJ": 2}  # só relevantes
        assert cliente.get("/api/estados", params={"q": "instrutoria"}).json() == {"MG": 1, "RJ": 1}
