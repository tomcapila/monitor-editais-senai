from __future__ import annotations

import io
import logging
import re
from datetime import date

import httpx
import pdfplumber

from .coletores.base import USER_AGENT, parse_data

log = logging.getLogger(__name__)

# Heurística: data que aparece perto de palavras ligadas a prazo de inscrição.
_PRAZO = re.compile(
    r"(inscri[cç][aãoõ]\w*|propostas?|encerramento)([^\n]{0,160})",
    re.IGNORECASE,
)
_DATAS = re.compile(r"\d{2}/\d{2}/\d{4}")


def extrair_texto_pdf(url: str, max_paginas: int = 5, timeout: int = 60) -> str:
    """Baixa o PDF e devolve o texto das primeiras páginas ('' se não for PDF)."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        if b"%PDF" not in r.content[:1024]:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_paginas])
    except Exception as e:
        log.warning("Falha ao ler PDF %s: %s", url, e)
        return ""


def achar_prazo(texto: str) -> date | None:
    """Tenta achar o prazo de inscrição. É heurístico: confira no edital."""
    datas = [
        parse_data(d)
        for m in _PRAZO.finditer(texto)
        for d in _DATAS.findall(m.group(2))
    ]
    datas = [d for d in datas if d]
    return max(datas) if datas else None
