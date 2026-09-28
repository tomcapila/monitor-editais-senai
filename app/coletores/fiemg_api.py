"""
Coletor do Portal de Compras FIEMG pelo serviço JSON do próprio portal.

O mural preenche as tabelas chamando WebService/Servicos.asmx (ASMX, JSON).
Em vez de ler o HTML, abrimos a página uma vez no Playwright (o site passa
por uma verificação do Cloudflare, que um httpx puro provavelmente não
passaria) e fazemos as mesmas chamadas com fetch() de dentro da página,
aproveitando cookies e sessão. Resultado: dados completos, com datas,
e paginação além dos 50 registros que a tela mostra.

Os métodos e payloads abaixo foram copiados das chamadas que o próprio
portal faz (diagnóstico de 27/09/2026, telas nNmTela=E e nNmTela=ES).
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)

URL_MURAL = "https://compras.fiemg.com.br/portal/Mural.aspx"

# Payload do mural (tela "Edital", nNmTela=E): tmpTipoMuralProcesso 2 = EDITAL.
_DTO_MURAL = {
    "nAnoFinalizacao": 0, "tmpTipoMuralProcesso": 2, "nCdModulo": 0, "nCdModalidade": 0,
    "nCdModalidadeFase": 0, "nCdTipoModalidade": 0, "tmpTipoMuralVisao": 0,
    "nCdSituacao": 0, "nCdTipoProcesso": 0, "nCdEmpresa": 0, "sNrProcesso": "",
    "nCdProcesso": 0, "sDsObjeto": "", "sDtPeriodoDe": "", "sDtPeriodoAte": "",
    "sOrdenarPor": "NCDPROCESSO", "sOrdenarPorDirecao": "DESC",
    "dtoPaginacao": {"nPaginaDe": 1, "nPaginaAte": 50}, "dtoIdioma": {"nCdIdioma": 1},
}

# Payload da tela "Edital simplificado" (nNmTela=ES): tmpTipoMuralProcesso 3.
# nCdEditalTipo 2 = editais de cadastro (chamamentos), 3 = RFI.
_DTO_SIMPLIFICADO = {
    "tmpTipoMuralProcesso": 3, "nCdEmpresa": 0,
    "sOrdenarPor": "TDTINICIAL", "sOrdenarPorDirecao": "DESC",
    "dtoPaginacao": {"nPaginaDe": 1, "nPaginaAte": 50}, "dtoIdioma": {"nCdIdioma": 1},
    "bFlEmAndamento": True, "bFlPesquisaFornecedores": False,
}

LISTAS = {
    "mural": {
        "rotulo": "Mural de processos",
        "metodo": "PesquisarProcessos",
        "dto": _DTO_MURAL,
    },
    "chamamentos": {
        "rotulo": "Chamamentos públicos em andamento",
        "metodo": "PesquisarProcessosEditalSimplificado",
        "dto": {**_DTO_SIMPLIFICADO, "nCdEditalTipo": 2},
        "tipo": "Chamamento público",
    },
    "rfis": {
        "rotulo": "RFIs em andamento",
        "metodo": "PesquisarProcessosEditalSimplificado",
        "dto": {**_DTO_SIMPLIFICADO, "nCdEditalTipo": 3},
        "tipo": "RFI",
    },
}

# fetch() de dentro da página, com AbortController para respeitar o timeout.
JS_CONSULTA = """
async ({metodo, dto, timeoutMs}) => {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch('WebService/Servicos.asmx/' + metodo, {
      method: 'POST',
      headers: {'Content-Type': 'application/json; charset=utf-8'},
      body: '{dtoProcesso:' + JSON.stringify(dto) + '}',
      signal: ctrl.signal,
    });
    if (!r.ok) throw new Error('HTTP ' + r.status + ' em ' + metodo);
    return (await r.json()).d || [];
  } finally {
    clearTimeout(t);
  }
}
"""

VALORES_VAZIOS = {"", "nao informado", "não informado"}
_DATA_NET = re.compile(r"/Date\((-?\d+)")
_EPOCA = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
_MS_1900 = -2208988800000  # 01/01/1900 em ms; abaixo disso é "sem data"


def _texto(v) -> str:
    # o portal manda códigos de controle em alguns campos (ex.: sDsSituacao
    # do mural vem como ""); isso não é texto
    s = "".join(c for c in str(v or "") if c.isprintable() or c.isspace())
    s = " ".join(s.split())
    return "" if s.lower() in VALORES_VAZIOS else s


def parse_data_portal(v) -> date | None:
    """Aceita /Date(ms)/ do ASP.NET, dd/mm/aaaa e ISO (aaaa-mm-dd...)."""
    if not v:
        return None
    s = str(v)
    m = _DATA_NET.search(s)
    if m:
        # aritmética em vez de fromtimestamp(), que falha com negativos no Windows;
        # o portal manda DateTime.MinValue (/Date(-62135...)/) para "sem data"
        ms = int(m.group(1))
        if ms < _MS_1900:
            return None
        return (_EPOCA + timedelta(milliseconds=ms)).astimezone(_BRASILIA).date()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    return parse_data(s)


def link_processo(reg: dict) -> str:
    """Link que abre o processo no mural (a página lê esses parâmetros da URL)."""
    params = {"nNmTela": "E", "nCdProcesso": reg.get("nCdProcesso")}
    if reg.get("nCdModulo"):
        params["nCdModulo"] = reg["nCdModulo"]
    return f"{URL_MURAL}?{urlencode(params)}"


def registro_para_edital(reg: dict, lista: str, fonte_nome: str) -> Edital | None:
    cod = reg.get("nCdProcesso")
    if not cod:
        return None
    numero = _texto(reg.get("sNrEdital")) or _texto(reg.get("sNrProcessoDisplay"))
    objeto = _texto(reg.get("sDsObjeto")) or _texto(reg.get("sDsClasse"))
    titulo = _texto(reg.get("sDsTitulo")) or numero or objeto[:140]
    if not titulo:
        return None
    return Edital(
        fonte=fonte_nome,
        id_externo=str(cod),
        titulo=titulo,
        objeto=objeto,
        url=link_processo(reg),
        # sNmEmpresa traz a unidade real (ex.: "SESI/DRMG - SEDE"); o apelido
        # costuma ser só "SISTEMA FIEMG"
        unidade=_texto(reg.get("sNmEmpresa")) or _texto(reg.get("sNmApelido")),
        tipo=_texto(reg.get("sNmModalidade")) or LISTAS[lista].get("tipo", ""),
        situacao=_texto(reg.get("sDsSituacao")),
        data_publicacao=parse_data_portal(reg.get("tDtInicial") or reg.get("sDtInicioVigencia")),
        prazo=parse_data_portal(reg.get("sDtFimVigencia") or reg.get("tDtFinal")),
    )


class ColetorFiemgApi(Coletor):
    def coletar(self) -> list[Edital]:
        listas = self.fonte.get("listas", list(LISTAS))
        por_pagina = int(self.fonte.get("por_pagina", 50))
        max_registros = int(self.fonte.get("max_registros", 200))
        paginas = max(1, -(-max_registros // por_pagina))
        # total estimado de chamadas, para a barra de progresso
        total = 1 + sum(paginas if n == "mural" else 1 for n in listas)
        feitos = 0

        resultados: dict[str, Edital] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                self.progresso.passo("Abrindo o portal", feitos, total)
                page.goto(self.url or f"{URL_MURAL}?nNmTela=E",
                          wait_until="networkidle", timeout=self.timeout_ms())
                feitos += 1

                for nome in listas:
                    lista = LISTAS[nome]
                    # listas simplificadas: uma página basta (hoje vêm vazias)
                    n_paginas = paginas if nome == "mural" else 1
                    for pag in range(n_paginas):
                        de = pag * por_pagina + 1
                        ate = min((pag + 1) * por_pagina, max_registros)
                        self.progresso.passo(
                            f"{lista['rotulo']}: registros {de} a {ate}", feitos, total)
                        dto = copy.deepcopy(lista["dto"])
                        dto["dtoPaginacao"] = {"nPaginaDe": de, "nPaginaAte": ate}
                        timeout = self.timeout_ms()
                        page.set_default_timeout(timeout + 5000)
                        registros = page.evaluate(
                            JS_CONSULTA,
                            {"metodo": lista["metodo"], "dto": dto, "timeoutMs": timeout},
                        )
                        feitos += 1
                        for reg in registros:
                            try:
                                ed = registro_para_edital(reg, nome, self.nome)
                            except Exception as e:  # um registro estranho não derruba a fonte
                                log.warning("Registro ignorado (%s): %s", e, reg.get("nCdProcesso"))
                                continue
                            if ed:
                                resultados[ed.chave] = ed
                        log.info("%s %d-%d: %d registros", nome, de, ate, len(registros))
                        if len(registros) < ate - de + 1:
                            feitos += n_paginas - pag - 1  # acabou antes do máximo
                            break
            finally:
                browser.close()
        self.progresso.passo(f"{len(resultados)} editais lidos", total, total)
        return list(resultados.values())
