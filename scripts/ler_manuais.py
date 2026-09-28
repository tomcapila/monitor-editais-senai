"""
Baixa manuais de marca em PDF e mostra o que dizem sobre cores: as linhas com
Pantone, CMYK, RGB ou hexadecimal (com a página) e as cores de preenchimento
mais usadas nessas páginas (as amostras de cor do manual).

    python scripts/ler_manuais.py URL [URL ...]

Usado uma vez para achar as cores oficiais do SENAI e do Sebrae para o painel.
"""
import io
import re
import sys
from collections import Counter

import httpx
import pdfplumber

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PISTA = re.compile(r"pantone|cmyk|rgb|hexa|html|#\s?[0-9a-f]{6}\b|\bweb\b|\bcor(es)?\b",
                   re.IGNORECASE)


def para_hex(cor) -> str | None:
    """Cor do pdfplumber (cinza, RGB ou CMYK, de 0 a 1) em #rrggbb."""
    if cor is None:
        return None
    if isinstance(cor, (int, float)):
        cor = (cor,)
    cor = tuple(float(c) for c in cor if isinstance(c, (int, float)))
    if len(cor) == 1:
        r = g = b = cor[0]
    elif len(cor) == 3:
        r, g, b = cor
    elif len(cor) == 4:
        c, m, y, k = cor
        r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    else:
        return None
    return "#" + "".join(f"{round(max(0, min(1, v)) * 255):02X}" for v in (r, g, b))


def ler(url: str) -> None:
    print(f"=== {url}", flush=True)
    try:
        r = httpx.get(url, timeout=120, follow_redirects=True, headers={"User-Agent": UA})
    except Exception as e:
        print(f"FALHOU: {type(e).__name__}: {e}\n")
        return
    print(f"HTTP {r.status_code} [{r.headers.get('content-type', '')}] "
          f"{len(r.content)} bytes; final: {r.url}")
    if b"%PDF" not in r.content[:1024]:
        print("não é PDF\n")
        return
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print(f"{len(pdf.pages)} páginas")
        for n, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text() or ""
            linhas = [" ".join(ln.split()) for ln in texto.splitlines() if PISTA.search(ln)]
            if not any(re.search(r"pantone|cmyk|rgb|hexa|#\s?[0-9a-f]{6}", ln, re.I)
                       for ln in linhas):
                continue
            print(f"\n-- página {n}")
            for ln in linhas[:40]:
                print(f"   {ln[:200]}")
            cores = Counter()
            for obj in pagina.rects + pagina.curves:
                h = para_hex(obj.get("non_stroking_color"))
                if h and h not in ("#FFFFFF", "#000000"):
                    cores[h] += 1
            if cores:
                print(f"   preenchimentos: {cores.most_common(12)}")
    print(flush=True)


if __name__ == "__main__":
    for u in sys.argv[1:]:
        ler(u)
