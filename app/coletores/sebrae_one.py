"""
Coletor do Sebrae One, a plataforma de credenciamento do Sebrae Minas
(credenciamento.sebraemg.com.br). As páginas buscam os dados numa API pública
(api-credenciamento.sebraemg.com.br/api/editais-public), com todos os editais
e, dentro de cada um, os "processos": as chamadas de credenciamento abertas
naquele edital (diagnóstico de 28/09/2026).

Os editais costumam ser permanentes; o que muda são as chamadas. Por isso cada
chamada vira um item (uma chamada nova gera alerta), e um edital sem chamada
entra como um item só.
"""
from __future__ import annotations

import logging
from collections import Counter

import httpx

from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)

URL_API = "https://api-credenciamento.sebraemg.com.br/api/editais-public"
URL_SITE = "https://credenciamento.sebraemg.com.br"

# status do edital na API; "A" é o único visto no diagnóstico
SITUACOES = {"A": "Aberto", "E": "Encerrado", "F": "Encerrado", "C": "Cancelado",
             "S": "Suspenso", "I": "Inativo"}


def _texto(v) -> str:
    return " ".join(str(v or "").split())


def _data(v):
    """A API usa aaaa-mm-dd hh:mm:ss (ou ISO); parse_data espera dd/mm/aaaa."""
    t = _texto(v)[:10]
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return parse_data(f"{t[8:10]}/{t[5:7]}/{t[:4]}")
    return parse_data(t)


def editais_para_itens(editais: list[dict], fonte_nome: str) -> list[Edital]:
    itens = []
    for ed in editais:
        ident = _texto(ed.get("id"))
        titulo = _texto(ed.get("titulo"))
        if not ident or not titulo:
            continue
        codigo = _texto(ed.get("codigo_ano"))
        nome = f"Edital {codigo}: {titulo}" if codigo else titulo
        base = dict(
            fonte=fonte_nome,
            url=f"{URL_SITE}/edital/{ident}",
            unidade="Sebrae Minas",
            tipo="Credenciamento",
            situacao=SITUACOES.get(_texto(ed.get("status")), _texto(ed.get("status"))),
        )
        processos = [p for p in ed.get("processos") or [] if isinstance(p, dict)]
        if not processos:
            itens.append(Edital(
                id_externo=f"edital-{ident}", titulo=nome,
                objeto=_texto(ed.get("resumo") or ed.get("texto")),
                data_publicacao=_data(ed.get("data_abertura")), **base))
            continue
        for proc in processos:
            pid = _texto(proc.get("id"))
            if not pid:
                continue
            itens.append(Edital(
                id_externo=f"processo-{pid}",
                titulo=f"{nome} · {_texto(proc.get('titulo'))}".rstrip(" ·"),
                objeto=_texto(proc.get("descricao")) or _texto(ed.get("resumo")),
                data_publicacao=_data(proc.get("data_inicio") or proc.get("created_at")
                                      or ed.get("data_abertura")),
                prazo=_data(proc.get("data_fim") or proc.get("data_fechamento")),
                **base))
    return itens


class ColetorSebraeOne(Coletor):
    def coletar(self) -> list[Edital]:
        api = self.fonte.get("api") or URL_API
        self.progresso.passo("Lendo os editais do Sebrae One")
        r = httpx.get(api, timeout=self.timeout_ms() / 1000, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                               "Origin": URL_SITE, "Referer": URL_SITE + "/"})
        r.raise_for_status()
        dados = r.json()
        editais = dados.get("data") if isinstance(dados, dict) else dados
        editais = [e for e in editais or [] if isinstance(e, dict)]
        processos = [p for e in editais for p in e.get("processos") or [] if isinstance(p, dict)]
        log.info("%s: %d editais, %d chamadas; status %s; campos da chamada %s",
                 self.nome, len(editais), len(processos),
                 Counter(_texto(e.get("status")) for e in editais),
                 sorted(processos[0]) if processos else [])
        return editais_para_itens(editais, self.nome)
