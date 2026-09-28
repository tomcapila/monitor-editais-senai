"""
Servidor do painel.  Rodar com:  uvicorn app.main:app --reload
Depois abra http://localhost:8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, diagnostico
from .coleta import executar_coleta, progresso
from .config import STATIC_DIR, carregar_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
agendador = BackgroundScheduler(timezone="America/Sao_Paulo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.iniciar()
    horas = carregar_config().get("coleta", {}).get("intervalo_horas", 12)
    agendador.add_job(executar_coleta, "interval", hours=horas, id="coleta",
                      max_instances=1, coalesce=True)
    agendador.start()
    yield
    agendador.shutdown(wait=False)


app = FastAPI(title="Monitor de editais SENAI", lifespan=lifespan)
diagnostico.SAIDA.mkdir(exist_ok=True)
app.mount("/diagnostico-arquivos", StaticFiles(directory=diagnostico.SAIDA), name="diag")


@app.get("/")
def pagina():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/editais")
def api_editais(q: str = "", relevantes: bool = True, abertos: bool = True,
                senai: bool = False):
    return db.listar(q, relevantes, abertos, senai)


@app.get("/api/resumo")
def api_resumo(desde: str | None = None):
    return db.resumo(desde)


@app.get("/api/filtro")
def api_filtro():
    """Termos do filtro, para o painel grifar no texto o que tornou o edital relevante."""
    filtro = carregar_config().get("filtro", {})
    return {"termos_relevantes": filtro.get("termos_relevantes", [])}


@app.post("/api/coletar")
def api_coletar(tarefas: BackgroundTasks):
    if progresso.rodando:
        return {"status": "ja_rodando"}
    tarefas.add_task(executar_coleta)
    return {"status": "iniciada"}


@app.get("/api/status")
def api_status():
    job = agendador.get_job("coleta")
    return {
        "rodando": progresso.rodando,
        "progresso": progresso.estado(),
        "ultima": db.ultima_execucao(),
        "proxima": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


@app.post("/api/diagnostico")
def api_rodar_diagnostico(tarefas: BackgroundTasks):
    if diagnostico.progresso.rodando:
        return {"status": "ja_rodando"}
    tarefas.add_task(diagnostico.rodar)
    return {"status": "iniciado"}


@app.get("/api/diagnostico")
def api_ver_diagnostico():
    return {
        "rodando": diagnostico.progresso.rodando,
        "progresso": diagnostico.progresso.estado(),
        "erro": diagnostico.estado["erro"],
        "resultado": diagnostico.ultimo_resultado(),
    }
