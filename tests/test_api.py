from fastapi.testclient import TestClient

from app import db
from app.coleta import executar_coleta
from app.main import app


def test_api(config_demo):
    executar_coleta()
    with TestClient(app) as cliente:
        relevantes = cliente.get("/api/editais").json()
        assert len(relevantes) == 2
        assert not any("Aquisição de equipamentos" in e["titulo"] for e in relevantes)

        todos = cliente.get("/api/editais", params={"relevantes": "false", "abertos": "false"}).json()
        assert len(todos) == 3

        status = cliente.get("/api/status").json()
        assert status["ultima"]["encontrados"] == 3
        assert status["ultima"]["novos"] == 3
        assert status["progresso"] == {"rodando": False}

        assert cliente.get("/").status_code == 200

        resumo = cliente.get("/api/resumo").json()
        assert resumo["total"] == 3 and resumo["relevantes"] == 2 and resumo["com_prazo"] == 2
        # a primeira coleta é a carga inicial: o que ela trouxe não é "novo"
        assert resumo["novos"] == 0 and resumo["pos_carga"] == 0
        assert all(e["da_carga"] == 1 and e["uf"] == "MG" for e in todos)

        # um processo relevante que chega depois conta como novo...
        with db.conectar() as con:
            con.execute("UPDATE editais SET primeiro_visto = '2999-01-01T00:00:00', da_carga = 0"
                        " WHERE id_externo = 'demo-1'")
        resumo = cliente.get("/api/resumo").json()
        assert resumo["novos"] == 1 and resumo["pos_carga"] == 1
        # ...mas não para quem visitou o painel depois da chegada dele
        resumo = cliente.get("/api/resumo", params={"desde": "2999-01-02T00:00:00"}).json()
        assert resumo["novos"] == 0

        termos = cliente.get("/api/filtro").json()["termos_relevantes"]
        assert "consultoria" in termos
