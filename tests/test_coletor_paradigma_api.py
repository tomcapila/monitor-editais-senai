from datetime import date, datetime

from app.coletores.paradigma_api import (link_processo, mural, parse_data_portal,
                                         registro_para_edital, unidade)
from tests.test_diagnostico import portal  # noqa: F401 (fixture do portal falso)


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


def test_registro_da_firjan():
    # formato do Portal de Compras Firjan (diagnóstico de 28/09/2026)
    reg = {"nCdProcesso": 14306, "nCdModulo": 19, "sNrProcessoDisplay": "CD003282026",
           "sNrEdital": "002001", "sDsTitulo": None,
           "sDsObjeto": "AQUISICAO DE NOTEBOOK PARA ATENDIMENTO A UNIDADE SENAI IST EDI",
           "sNmEmpresa": "03.848.688/0009-00 - IST AUTOMAÇÃO", "sNmApelido": "SENAI",
           "sNmModalidade": "Compra direta", "sDsSituacao": "\u0013\u0012\u0012\u0013",
           "tDtInicial": "/Date(1790305200000)/", "tDtFinal": "/Date(-62135589600000)/"}
    base = mural("https://portaldecompras.firjan.com.br/portal/Mural.aspx?nNmTela=E")
    assert base == "https://portaldecompras.firjan.com.br/portal/Mural.aspx"

    ed = registro_para_edital(reg, "mural", "Portal de Compras Firjan", base,
                              apelido_na_unidade=True)
    assert ed.url.startswith("https://portaldecompras.firjan.com.br/portal/Mural.aspx?")
    assert "nCdProcesso=14306" in ed.url and "nCdModulo=19" in ed.url
    assert ed.unidade == "SENAI - IST AUTOMAÇÃO"
    assert ed.titulo == "002001"
    assert ed.situacao == ""
    assert ed.prazo is None  # o portal manda DateTime.MinValue


def test_unidade():
    fiemg = {"sNmEmpresa": "SESI/DRMG - SEDE", "sNmApelido": "SISTEMA FIEMG"}
    assert unidade(fiemg) == "SESI/DRMG - SEDE"
    firjan = {"sNmEmpresa": "03.851.171/0006-27 - SESI TRÊS RIOS", "sNmApelido": "SESI"}
    assert unidade(firjan) == "SESI TRÊS RIOS"
    # o apelido não se repete quando o nome já traz a entidade
    assert unidade(firjan, apelido_na_unidade=True) == "SESI TRÊS RIOS"
    assert unidade({"sNmEmpresa": "03.848.688/0063-55 - ISI QUÍMICA VERDE",
                    "sNmApelido": "SENAI"}, True) == "SENAI - ISI QUÍMICA VERDE"
    assert unidade({"sNmEmpresa": "", "sNmApelido": "SENAI"}) == "SENAI"


def test_coletor_em_outro_portal(portal):
    """O coletor segue o endereço da fonte: link e serviço do próprio portal."""
    from app.coletores.paradigma_api import ColetorParadigmaApi

    fonte = {"nome": "Portal de teste", "url": f"{portal}/portal/Mural.aspx?nNmTela=E",
             "listas": ["mural", "rfis"], "max_registros": 2, "por_pagina": 2}
    editais = ColetorParadigmaApi(fonte, {"coleta": {"timeout_segundos": 30}}).coletar()

    assert len(editais) == 1
    ed = editais[0]
    assert ed.url.startswith(f"{portal}/portal/Mural.aspx?nNmTela=E&nCdProcesso=777")
    assert ed.unidade == "SENAI/RJ - SEDE"
