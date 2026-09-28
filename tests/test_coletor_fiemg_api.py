from datetime import date, datetime

from app.coletores.fiemg_api import link_processo, parse_data_portal, registro_para_edital


def test_parse_data_portal():
    ms = int(datetime(2026, 10, 31, 12, 0).timestamp() * 1000)
    assert parse_data_portal(f"/Date({ms})/") == date(2026, 10, 31)
    assert parse_data_portal("31/10/2026 17:00:00") == date(2026, 10, 31)
    assert parse_data_portal("2026-10-31T17:00:00") == date(2026, 10, 31)
    assert parse_data_portal(None) is None
    # DateTime.MinValue do .NET: o portal usa para "sem data" (quebrava no Windows)
    assert parse_data_portal("/Date(-62135596800000)/") is None


def test_registro_do_mural():
    # nomes de campos de PesquisarProcessos (vistos no diagnóstico); valores fictícios
    reg = {"nCdProcesso": 20600, "nCdModulo": 53, "sNrProcessoDisplay": "CRED 2026000012",
           "sNrEdital": "CRED 2026000012", "sDsTitulo": "",
           "sDsObjeto": "Seleção e o credenciamento de pessoas jurídicas",
           "sNmEmpresa": "SESI BH", "sNmApelido": "SISTEMA FIEMG", "sNmModalidade": "Credenciamento",
           "sDsSituacao": "", "tDtInicial": "01/09/2026 08:00:00",
           "tDtFinal": "30/10/2026 17:00:00"}
    ed = registro_para_edital(reg, "mural", "Portal")
    assert ed.id_externo == "20600"
    assert ed.titulo == "CRED 2026000012"  # título vazio cai para o número
    assert ed.unidade == "SESI BH"  # a empresa vem antes do apelido genérico
    assert ed.situacao == ""  # códigos de controle do portal são descartados
    assert ed.tipo == "Credenciamento"
    assert ed.data_publicacao == date(2026, 9, 1)
    assert ed.prazo == date(2026, 10, 30)
    assert ed.url == link_processo(reg)
    assert "nCdProcesso=20600" in ed.url and "nCdModulo=53" in ed.url


def test_registro_de_chamamento():
    # campos usados pelo template da tela "Edital simplificado"
    reg = {"nCdProcesso": 7, "sNrEdital": "CP 01/2026", "sDsClasse": "Consultoria",
           "sDtInicioVigencia": "01/10/2026 00:00:00", "sDtFimVigencia": None}
    ed = registro_para_edital(reg, "chamamentos", "Portal")
    assert ed.titulo == "CP 01/2026" and ed.objeto == "Consultoria"
    assert ed.tipo == "Chamamento público"
    assert ed.prazo is None  # o portal mostra "Indeterminado"


def test_registro_sem_codigo_e_ignorado():
    assert registro_para_edital({"sNrEdital": "x"}, "mural", "Portal") is None
