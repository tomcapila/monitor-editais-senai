import time

import pytest

from app import db
from app.coleta import executar_coleta
from app.progresso import Progresso, TempoEsgotado


def test_percentual_combina_fase_e_passo():
    p = Progresso()
    p.iniciar(60, total_fases=4)
    p.fase("Coletando", 1)
    p.passo("página 1 de 2", 1, 2)
    e = p.estado()
    assert e["rodando"] and e["percentual"] == 38  # (1 + 1/2) / 4
    assert e["etapa"] == "Coletando" and e["limite_s"] == 60
    p.finalizar()
    assert p.estado() == {"rodando": False}


def test_tempo_esgotado_e_restante():
    p = Progresso()
    p.iniciar(0.05)
    assert p.restante_ms(60000) == 1000  # resta ~50 ms; o mínimo é 1 s
    time.sleep(0.1)
    with pytest.raises(TempoEsgotado, match="Tempo limite"):
        p.fase("Etapa lenta", 0)


def test_sem_progresso_nao_tem_limite():
    p = Progresso()  # nunca iniciado: operações usam o timeout próprio
    p.verificar()
    assert p.restante_ms(5000) == 5000


def test_coleta_interrompida_pelo_limite(config_demo):
    config_demo["coleta"]["tempo_limite_segundos"] = 0
    r = executar_coleta()
    assert r["status"] == "tempo_esgotado"
    assert "Tempo limite" in r["erros"][0]
    assert "Tempo limite" in db.ultima_execucao()["erros"]
