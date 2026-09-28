"""
Roda todas as fontes ativas, filtra, salva e alerta.
Também pode ser executado direto:  python -m app.coleta
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime

from . import alertas, db
from .coletores import criar_coletor
from .config import carregar_config
from .filtro import avaliar
from .pdf_utils import achar_prazo, extrair_texto_pdf
from .progresso import Progresso, TempoEsgotado

log = logging.getLogger(__name__)

_lock = threading.Lock()
progresso = Progresso()


def resumir_erro(e: Exception) -> str:
    """Uma linha legível para o painel; o detalhe completo fica no log.

    Uma linha só por erro: o painel separa as fontes pelas quebras de linha.
    """
    codigo = getattr(getattr(e, "response", None), "status_code", None)
    if not codigo:
        # erros do Playwright só trazem o código no texto ("HTTP 403 em PesquisarProcessos")
        m = re.search(r"\bHTTP (\d{3})\b", str(e))
        codigo = int(m.group(1)) if m else None
    if codigo in (401, 403):
        return f"o site recusou o acesso (HTTP {codigo})"
    if codigo:
        return f"o site respondeu com erro (HTTP {codigo})"
    nome = type(e).__name__  # por nome, para não acoplar a httpx/Playwright
    if "Timeout" in nome:
        return "o site demorou demais para responder"
    if nome == "ConnectError":
        return "não foi possível conectar ao site"
    return ((str(e).strip().splitlines() or [nome])[0])[:200]


def executar_coleta() -> dict:
    if not _lock.acquire(blocking=False):
        return {"status": "ja_rodando"}
    config = carregar_config()
    opts = config.get("coleta", {})
    fontes = [f for f in config.get("fontes", []) if f.get("ativo", True)]
    # fases: coletar e processar cada fonte, e enviar alertas no fim
    total_fases = 2 * len(fontes) + 1
    progresso.iniciar(opts.get("tempo_limite_segundos", 600), total_fases)
    inicio = datetime.now().isoformat(timespec="seconds")
    encontrados, novos, erros, para_alertar = 0, 0, [], []
    status = "ok"
    try:
        db.iniciar()
        primeira_vez = db.vazio()  # não dispara alerta em massa na 1ª coleta

        try:
            for i, fonte in enumerate(fontes):
                progresso.fase(f"Coletando: {fonte['nome']}", 2 * i)
                log.info("Coletando: %s", fonte["nome"])
                try:
                    editais = criar_coletor(fonte, config, progresso).coletar()
                except TempoEsgotado:
                    raise
                except Exception as e:
                    progresso.verificar()  # timeout do Playwright pode ter sido o limite total
                    log.exception("Erro na fonte %s", fonte["nome"])
                    erros.append(f"{fonte['nome']}: {resumir_erro(e)}")
                    continue

                progresso.fase(f"Processando: {fonte['nome']}", 2 * i + 1)
                for n, ed in enumerate(editais, start=1):
                    progresso.passo(f"Edital {n} de {len(editais)}", n - 1, len(editais))
                    encontrados += 1
                    eh_pdf = ed.url.lower().split("?")[0].endswith(".pdf")
                    if opts.get("ler_pdfs") and eh_pdf and not db.existe(ed.chave):
                        progresso.passo(f"Lendo PDF do edital {n} de {len(editais)}",
                                        n - 1, len(editais))
                        ed.texto_extra = extrair_texto_pdf(
                            ed.url, opts.get("max_paginas_pdf", 5),
                            progresso.restante_ms(opts.get("timeout_segundos", 60) * 1000) / 1000,
                        )
                        ed.prazo = ed.prazo or achar_prazo(ed.texto_extra)
                    avaliar(ed, config.get("filtro", {}))
                    if db.salvar(ed):
                        novos += 1
                        if ed.relevante and not primeira_vez:
                            para_alertar.append(ed)
        except TempoEsgotado as e:
            # o que já foi salvo fica; os alertas abaixo ainda são enviados
            log.error("%s", e)
            erros.append(str(e))
            status = "tempo_esgotado"

        if para_alertar:
            progresso.sem_limite()  # alertas têm timeout próprio e não podem se perder
            progresso.fase("Enviando alertas", total_fases - 1)
            if alertas.enviar(para_alertar, config.get("alertas", {})):
                db.marcar_notificados([e.chave for e in para_alertar])
    finally:
        fim = datetime.now().isoformat(timespec="seconds")
        db.registrar_execucao(inicio, fim, encontrados, novos, erros)
        progresso.finalizar()
        _lock.release()

    resultado = {"status": status, "encontrados": encontrados, "novos": novos,
                 "alertados": len(para_alertar), "erros": erros}
    log.info("Coleta concluída: %s", resultado)
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(executar_coleta())
