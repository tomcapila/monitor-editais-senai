"""
Diagnóstico de vários portais de uma vez, sem janela. Imprime um relatório
(tabelas, links com cara de edital, chamadas AJAX e, em portais Paradigma, o
teste do serviço JSON) e salva os arquivos em diagnostico/portais/<site>/.

    python scripts/diagnostico_portais.py URL [URL ...]

É o que o workflow "Diagnóstico de portais" roda no GitHub Actions.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.diagnostico import SAIDA, relatorio, rodar  # noqa: E402


def pasta(url: str) -> str:
    """Nome de pasta legível e único por URL (host + caminho + consulta)."""
    nome = re.sub(r"^https?://", "", url)
    return re.sub(r"[^A-Za-z0-9.-]+", "_", nome).strip("_")[:120]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--limite", type=float, default=180, help="segundos por portal")
    args = ap.parse_args()

    falhas = 0
    for url in args.urls:
        r = rodar(url, limite_segundos=args.limite, saida=SAIDA / "portais" / pasta(url),
                  amostra_max=6000)
        falhas += r["status"] != "ok"
        print(relatorio(r), end="\n\n", flush=True)
    print(f"{len(args.urls) - falhas} de {len(args.urls)} portais diagnosticados. "
          f"Arquivos em {SAIDA / 'portais'}")
    return 1 if falhas == len(args.urls) else 0


if __name__ == "__main__":
    sys.exit(main())
