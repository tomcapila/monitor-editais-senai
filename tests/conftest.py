import copy

import pytest

from app import coleta, config, db, main


@pytest.fixture
def config_demo(tmp_path, monkeypatch):
    """Banco temporário e config com só a fonte demo ativa (config.yaml não é alterado)."""
    cfg = copy.deepcopy(config.carregar_config())
    for fonte in cfg["fontes"]:
        fonte["ativo"] = fonte["tipo"] == "demo"
    cfg["alertas"] = {"telegram": False, "email": False}

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "editais.db")
    monkeypatch.setattr(coleta, "carregar_config", lambda: cfg)
    monkeypatch.setattr(main, "carregar_config", lambda: cfg)
    return cfg
