from __future__ import annotations

import unicodedata

from .coletores.base import Edital


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


# Situações de processo fechado (em ASCII, minúsculas: servem também no SQL
# de db.listar e no painel). Ex.: "Encerrado/Concluído" na transparência do SENAI-SP.
SITUACOES_ENCERRADAS = ("encerrad", "conclu", "cancelad", "revogad", "desert",
                        "fracassad", "anulad")


def encerrado(situacao: str) -> bool:
    texto = normalizar(situacao)
    return any(s in texto for s in SITUACOES_ENCERRADAS)


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
