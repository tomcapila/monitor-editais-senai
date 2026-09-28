from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH
from .coletores.base import Edital
from .filtro import SITUACOES_ENCERRADAS

SCHEMA = """
CREATE TABLE IF NOT EXISTS editais (
    chave TEXT PRIMARY KEY,
    fonte TEXT, id_externo TEXT, titulo TEXT, objeto TEXT, unidade TEXT, uf TEXT,
    instituicao TEXT,
    url TEXT, situacao TEXT, tipo TEXT,
    data_publicacao TEXT, prazo TEXT,
    relevancia INTEGER, relevante INTEGER, do_senai INTEGER,
    trecho_pdf TEXT,
    primeiro_visto TEXT, ultimo_visto TEXT,
    notificado INTEGER DEFAULT 0,
    da_carga INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT, fim TEXT, encontrados INTEGER, novos INTEGER, erros TEXT
);
"""


@contextmanager
def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conectar() as con:
        con.executescript(SCHEMA)
        _migrar(con)


def _migrar(con):
    """Atualiza bancos criados antes do suporte a vários estados."""
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(editais)")}
    if "uf" not in colunas:
        con.execute("ALTER TABLE editais ADD COLUMN uf TEXT")
        # até aqui o monitor só coletava em Minas Gerais
        con.execute("UPDATE editais SET uf = 'MG'")
    if "instituicao" not in colunas:
        con.execute("ALTER TABLE editais ADD COLUMN instituicao TEXT")
        # até aqui só havia portais do Sistema Indústria (SENAI, SESI, IEL...)
        con.execute("UPDATE editais SET instituicao = 'SENAI'")
    if "da_carga" not in colunas:
        con.execute("ALTER TABLE editais ADD COLUMN da_carga INTEGER DEFAULT 0")
        # antes a carga inicial era uma só: a primeira coleta que salvou algo
        carga = con.execute("SELECT MIN(fim) FROM execucoes WHERE novos > 0").fetchone()[0]
        con.execute("UPDATE editais SET da_carga = (primeiro_visto <= :c)", {"c": carga or ""})


def fonte_nova(fonte: str) -> bool:
    """True se a fonte ainda não tem nada salvo: a coleta dela é a carga inicial."""
    with conectar() as con:
        return con.execute("SELECT 1 FROM editais WHERE fonte = ? LIMIT 1",
                           (fonte,)).fetchone() is None


def existe(chave: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM editais WHERE chave = ?", (chave,)).fetchone() is not None


def salvar(ed: Edital, carga: bool = False) -> bool:
    """Insere ou atualiza. Devolve True se o edital é novo.

    'carga' marca o que veio na primeira coleta da fonte: já estava no portal
    antes do monitor, então não gera alerta nem aparece como novo no painel.
    """
    agora = datetime.now().isoformat(timespec="seconds")
    dados = {
        "chave": ed.chave, "fonte": ed.fonte, "id_externo": ed.id_externo,
        "titulo": ed.titulo, "objeto": ed.objeto, "unidade": ed.unidade,
        "uf": ed.uf or None, "instituicao": ed.instituicao or None, "url": ed.url, "situacao": ed.situacao, "tipo": ed.tipo,
        "data_publicacao": ed.data_publicacao.isoformat() if ed.data_publicacao else None,
        "prazo": ed.prazo.isoformat() if ed.prazo else None,
        "relevancia": ed.relevancia, "relevante": int(ed.relevante),
        "do_senai": int(ed.do_senai), "trecho_pdf": ed.texto_extra[:1500] or None,
        "da_carga": int(carga), "agora": agora,
    }
    with conectar() as con:
        existe = con.execute(
            "SELECT 1 FROM editais WHERE chave = ?", (ed.chave,)
        ).fetchone()
        if existe:
            con.execute(
                """UPDATE editais SET titulo=:titulo, objeto=:objeto, unidade=:unidade,
                   uf=COALESCE(:uf, uf), instituicao=COALESCE(:instituicao, instituicao), url=:url, situacao=:situacao, tipo=:tipo, prazo=COALESCE(:prazo, prazo),
                   relevancia=:relevancia, relevante=:relevante, do_senai=:do_senai,
                   trecho_pdf=COALESCE(:trecho_pdf, trecho_pdf), ultimo_visto=:agora
                   WHERE chave=:chave""",
                dados,
            )
            return False
        con.execute(
            """INSERT INTO editais (chave, fonte, id_externo, titulo, objeto, unidade, uf, instituicao,
               url, situacao, tipo, data_publicacao, prazo, relevancia, relevante,
               do_senai, trecho_pdf, primeiro_visto, ultimo_visto, da_carga)
               VALUES (:chave, :fonte, :id_externo, :titulo, :objeto, :unidade, :uf, :instituicao,
               :url, :situacao, :tipo, :data_publicacao, :prazo, :relevancia, :relevante,
               :do_senai, :trecho_pdf, :agora, :agora, :da_carga)""",
            dados,
        )
        return True


def marcar_notificados(chaves: list[str]):
    with conectar() as con:
        con.executemany(
            "UPDATE editais SET notificado = 1 WHERE chave = ?", [(c,) for c in chaves]
        )


# Filtro de instituição do painel. "SENAI" é só o que é do SENAI dentro dos
# portais do Sistema Indústria, que também trazem SESI, IEL e federações.
INSTITUICOES = {
    "SENAI": "instituicao = 'SENAI' AND do_senai = 1",
    "SEBRAE": "instituicao = 'SEBRAE'",
}


def _filtros(q="", apenas_relevantes=False, apenas_abertos=False, apenas_senai=False,
             uf="", inst="") -> tuple[str, list]:
    """Cláusula WHERE (com parâmetros) dos filtros do painel.
    apenas_senai é o filtro antigo "Só SENAI", o mesmo que inst="SENAI"."""
    where, params = [], []
    if q:
        where.append("(titulo || ' ' || COALESCE(objeto,'') || ' ' || COALESCE(unidade,'')) LIKE ?")
        params.append(f"%{q}%")
    if apenas_relevantes:
        where.append("relevante = 1")
    if apenas_abertos:
        where.append("(prazo IS NULL OR prazo >= date('now', 'localtime'))")
        for s in SITUACOES_ENCERRADAS:
            where.append(f"lower(COALESCE(situacao, '')) NOT LIKE '%{s}%'")
    inst = (inst or ("SENAI" if apenas_senai else "")).upper()
    if inst:
        where.append(INSTITUICOES.get(inst, "0"))  # instituição desconhecida: nada
    if uf:
        where.append("uf = ?")
        params.append(uf)
    return (" WHERE " + " AND ".join(where) if where else ""), params


def listar(q: str = "", apenas_relevantes=False, apenas_abertos=False,
           apenas_senai=False, limite: int = 500, uf: str = "", inst: str = "") -> list[dict]:
    where, params = _filtros(q, apenas_relevantes, apenas_abertos, apenas_senai, uf, inst)
    sql = "SELECT * FROM editais" + where
    sql += """ ORDER BY CASE
                 WHEN prazo IS NULL THEN 1
                 WHEN prazo < date('now', 'localtime') THEN 2
                 ELSE 0 END,
               prazo, primeiro_visto DESC LIMIT ?"""
    params.append(limite)
    with conectar() as con:
        return [dict(r) for r in con.execute(sql, params)]


def contagens(q: str = "", apenas_relevantes=False, apenas_abertos=False,
              uf: str = "", inst: str = "") -> dict:
    """Números dos botões do painel, com os mesmos filtros de listar().
    Cada grupo ignora o próprio filtro: os estados contam com a instituição
    escolhida e vice-versa. "" é o total do grupo (o botão Todos/Todas)."""
    with conectar() as con:
        where, params = _filtros(q, apenas_relevantes, apenas_abertos, inst=inst)
        ufs = dict(con.execute(
            f"SELECT uf, COUNT(*) FROM editais{where} GROUP BY uf", params).fetchall())
        ufs = {"": sum(ufs.values()), **{k: v for k, v in ufs.items() if k}}
        where, params = _filtros(q, apenas_relevantes, apenas_abertos, uf=uf)
        casos = ", ".join(f"COALESCE(SUM({cond}), 0)" for cond in INSTITUICOES.values())
        linha = con.execute(f"SELECT COUNT(*), {casos} FROM editais{where}", params).fetchone()
        insts = dict(zip(["", *INSTITUICOES], linha))
    return {"ufs": ufs, "instituicoes": insts}


def resumo(desde: str | None = None) -> dict:
    """Números para a frase do topo do painel.

    'desde' é a última visita do usuário (aaaa-mm-ddThh:mm:ss, hora local);
    sem ela, "novo" vale para as últimas 48 horas. O que veio na carga inicial
    de cada fonte nunca é novo.
    """
    with conectar() as con:
        r = con.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(relevante), 0) AS relevantes,
                      COALESCE(SUM(relevante AND do_senai AND instituicao = 'SENAI'), 0)
                          AS relevantes_senai,
                      COALESCE(SUM(relevante AND instituicao = 'SEBRAE'), 0) AS relevantes_sebrae,
                      COALESCE(SUM(relevante AND prazo IS NOT NULL), 0) AS com_prazo,
                      COALESCE(SUM(relevante AND NOT da_carga
                                   AND replace(primeiro_visto, 'T', ' ') > COALESCE(
                                       replace(:desde, 'T', ' '),
                                       datetime('now', 'localtime', '-2 days'))), 0) AS novos,
                      COALESCE(SUM(NOT da_carga), 0) AS pos_carga,
                      MIN(data_publicacao) AS publicacao_de,
                      MAX(data_publicacao) AS publicacao_ate
               FROM editais""",
            {"desde": desde},
        ).fetchone()
        ufs = dict(con.execute(
            "SELECT uf, COUNT(*) FROM editais WHERE uf IS NOT NULL GROUP BY uf").fetchall())
        return {**dict(r), "ufs": ufs}


def registrar_execucao(inicio: str, fim: str, encontrados: int, novos: int, erros: list[str]):
    with conectar() as con:
        con.execute(
            "INSERT INTO execucoes (inicio, fim, encontrados, novos, erros) VALUES (?,?,?,?,?)",
            (inicio, fim, encontrados, novos, "\n".join(erros) or None),
        )


def ultima_execucao() -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM execucoes ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None
