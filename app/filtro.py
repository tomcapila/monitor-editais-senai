from __future__ import annotations

import unicodedata

from .coletores.base import Edital


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


def avaliar(ed: Edital, cfg: dict) -> Edital:
    """Preenche relevancia, relevante e do_senai a partir do config."""
    texto = normalizar(ed.texto_busca())

    if any(normalizar(t) in texto for t in cfg.get("termos_excluir", [])):
        ed.relevancia = 0
    else:
        ed.relevancia = sum(
            1 for t in cfg.get("termos_relevantes", []) if normalizar(t) in texto
        )
    ed.relevante = ed.relevancia >= cfg.get("relevancia_minima", 1)
    ed.do_senai = any(normalizar(t) in texto for t in cfg.get("termos_orgao", []))
    return ed
