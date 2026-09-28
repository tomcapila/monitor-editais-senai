from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx

from .coletores.base import Edital

log = logging.getLogger(__name__)


def _resumo(editais: list[Edital]) -> str:
    linhas = [f"{len(editais)} edital(is) novo(s) relevante(s):", ""]
    for ed in editais[:20]:
        prazo = ed.prazo.strftime("%d/%m/%Y") if ed.prazo else "prazo não identificado"
        onde = " | ".join(filter(None, [ed.uf, ed.unidade or ed.fonte]))
        linhas += [f"• {ed.titulo}", f"  {onde} | {prazo}", f"  {ed.url}", ""]
    if len(editais) > 20:
        linhas.append(f"... e mais {len(editais) - 20}. Veja no painel.")
    return "\n".join(linhas)


def enviar(editais: list[Edital], cfg: dict) -> bool:
    """Devolve True se ao menos um canal enviou com sucesso."""
    if not editais:
        return False
    texto, ok = _resumo(editais), False

    if cfg.get("telegram"):
        token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            try:
                r = httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": texto[:4000],
                          "disable_web_page_preview": True},
                    timeout=30,
                )
                r.raise_for_status()
                ok = True
            except Exception as e:
                log.error("Falha no Telegram: %s", e)
        else:
            log.warning("Telegram ativado mas TELEGRAM_TOKEN/CHAT_ID não definidos")

    if cfg.get("email"):
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[Editais SENAI] {len(editais)} novo(s)"
            msg["From"] = os.environ["SMTP_USER"]
            msg["To"] = os.environ["EMAIL_PARA"]
            msg.set_content(texto)
            # "or": no GitHub Actions um segredo não cadastrado chega como texto vazio
            with smtplib.SMTP(os.getenv("SMTP_HOST") or "smtp.gmail.com",
                              int(os.getenv("SMTP_PORT") or "587")) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
            ok = True
        except Exception as e:
            log.error("Falha no e-mail: %s", e)

    return ok
