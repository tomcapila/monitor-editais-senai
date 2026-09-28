"""
Coletor genérico para páginas HTML simples que listam editais como links
(muito comum nos sites das federações). Serve de modelo para outros estados.
"""
from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import USER_AGENT, Coletor, Edital

PISTAS_LINK = ("edital", "credenciamento", "chamamento", "consultor", "instrutor")


class ColetorPaginaLinks(Coletor):
    def coletar(self) -> list[Edital]:
        self.progresso.passo("Baixando a página")
        r = httpx.get(
            self.url,
            timeout=self.timeout_ms() / 1000,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        vistos, editais = set(), []
        for a in soup.find_all("a", href=True):
            href = urljoin(str(r.url), a["href"])
            texto = " ".join(a.get_text(" ").split())
            alvo = f"{texto} {href}".lower()
            eh_pdf = href.lower().split("?")[0].endswith(".pdf")
            if not (eh_pdf or any(p in alvo for p in PISTAS_LINK)):
                continue
            if href in vistos or href.startswith(("mailto:", "javascript:")):
                continue
            vistos.add(href)
            titulo = texto or href.rsplit("/", 1)[-1]
            editais.append(
                Edital(
                    fonte=self.nome,
                    titulo=titulo[:200],
                    url=href,
                    id_externo=href,
                    unidade=self.fonte.get("unidade", ""),
                    tipo="PDF" if eh_pdf else "Página",
                )
            )
        return editais
