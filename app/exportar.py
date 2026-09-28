"""
Gera a versão estática do painel (para o GitHub Pages), sem servidor.
Rodar depois da coleta:  python -m app.exportar

Cria site/index.html (o mesmo painel) e site/dados.json. Quando encontra
dados.json ao lado, o painel filtra tudo no navegador em vez de chamar a API.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

from . import db
from .config import BASE_DIR, STATIC_DIR, carregar_config

SAIDA = BASE_DIR / "site"

# só o que o painel mostra ou usa para filtrar
CAMPOS = ("id_externo", "titulo", "objeto", "unidade", "uf", "instituicao", "url", "situacao",
          "tipo", "data_publicacao", "prazo", "relevante", "do_senai", "primeiro_visto",
          "da_carga")


def url_workflow() -> str | None:
    """Página do workflow no GitHub, para o botão "Coletar agora" do painel."""
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        return None
    servidor = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    return f"{servidor}/{repo}/actions/workflows/coleta.yml"


def exportar() -> dict:
    db.iniciar()
    editais = [{c: e[c] for c in CAMPOS} for e in db.listar(limite=100_000)]
    filtro = carregar_config().get("filtro", {})
    dados = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "ultima": db.ultima_execucao(),
        "termos_relevantes": filtro.get("termos_relevantes", []),
        "workflow_url": url_workflow(),
        "editais": editais,
    }
    SAIDA.mkdir(exist_ok=True)
    shutil.copyfile(STATIC_DIR / "index.html", SAIDA / "index.html")
    (SAIDA / "dados.json").write_text(
        json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"editais": len(editais), "pasta": str(SAIDA)}


if __name__ == "__main__":
    print(exportar())
