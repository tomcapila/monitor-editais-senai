from fastapi.testclient import TestClient

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
        assert resumo["total"] == 3 and resumo["relevantes"] == 2
        assert resumo["novos"] == 2 and resumo["com_prazo"] == 2

        termos = cliente.get("/api/filtro").json()["termos_relevantes"]
        assert "consultoria" in termos
