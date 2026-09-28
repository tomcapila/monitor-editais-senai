"""
Roda os coletores das fontes do config.yaml sem gravar nada no banco e mostra
o que cada um trouxe: total, relevantes, do SENAI e alguns exemplos.

    python scripts/testar_fontes.py                 # todas as fontes ativas
    python scripts/testar_fontes.py "Portal de Compras Firjan"

Serve para conferir uma fonte nova contra o portal real antes de ativá-la.
"""
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.coleta import resumir_erro  # noqa: E402
from app.coletores import criar_coletor  # noqa: E402
from app.config import carregar_config  # noqa: E402
from app.filtro import avaliar, encerrado  # noqa: E402
from app.progresso import Progresso  # noqa: E402


def main() -> int:
    # os coletores registram no log o que viram (campos, contagens, paginação)
    logging.basicConfig(level=logging.INFO, format="  log: %(message)s")
    config = carregar_config()
    nomes = sys.argv[1:]
    fontes = [f for f in config["fontes"]
              if (f["nome"] in nomes if nomes else f.get("ativo", True))]
    falhas = 0
    for fonte in fontes:
        print(f"=== {fonte['nome']} ({fonte['tipo']}, {fonte.get('uf', '?')}, "
              f"{fonte.get('instituicao', '?')})", flush=True)
        progresso = Progresso()
        progresso.iniciar(config.get("coleta", {}).get("tempo_limite_segundos", 600))
        try:
            editais = criar_coletor(fonte, config, progresso).coletar()
        except Exception as e:
            falhas += 1
            print(f"FALHOU: {resumir_erro(e)} ({type(e).__name__})\n", flush=True)
            continue
        finally:
            progresso.finalizar()
        for ed in editais:
            ed.uf = ed.uf or fonte.get("uf", "")
            ed.instituicao = ed.instituicao or fonte.get("instituicao", "")
            avaliar(ed, config.get("filtro", {}))
        relevantes = [e for e in editais if e.relevante]
        abertos = [e for e in relevantes if not encerrado(e.situacao)]
        print(f"{len(editais)} processos; {len(relevantes)} relevantes "
              f"({len(abertos)} não encerrados); {sum(e.do_senai for e in editais)} do SENAI")
        print(f"tipos: {Counter(e.tipo for e in editais).most_common(8)}")
        print(f"situações: {Counter(e.situacao for e in editais).most_common(8)}")
        print(f"unidades: {Counter(e.unidade for e in editais).most_common(8)}")
        print(f"com prazo: {sum(1 for e in editais if e.prazo)}; "
              f"links: {Counter(e.url.split('?')[0].split('#')[0] for e in editais).most_common(3)}")
        for e in (abertos or relevantes)[:12]:
            print(f"  - [{e.tipo}] {e.titulo[:90]} | {e.unidade} | {e.situacao} | {e.url[:120]}")
        print(flush=True)
    return 1 if fontes and falhas == len(fontes) else 0


if __name__ == "__main__":
    sys.exit(main())
