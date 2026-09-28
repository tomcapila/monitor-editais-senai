"""
Diagnóstico pelo terminal, com navegador visível.
Também dá para rodar pelo painel (botão "Rodar diagnóstico").

    python scripts/diagnostico_fiemg.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.diagnostico import rodar  # noqa: E402

r = rodar(visivel=True, pausa=lambda: input("Navegue à vontade. Enter para fechar..."))
if r["status"] != "ok":
    print("Falhou:", r.get("erro"))
    sys.exit(1)
print(f"{len(r['tabelas'])} tabelas encontradas:")
for t in r["tabelas"]:
    print(f"  #{t['indice']} ({t['total_linhas']} linhas): {t['headers'][:8]}")
print(f"{len(r['rede'])} chamadas AJAX. Arquivos salvos em diagnostico/")
