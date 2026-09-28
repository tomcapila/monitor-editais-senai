from app.coleta import executar_coleta


def test_coleta_demo(config_demo):
    r = executar_coleta()
    assert r["status"] == "ok"
    assert r["encontrados"] == 3
    assert r["novos"] == 3
    assert r["erros"] == []
