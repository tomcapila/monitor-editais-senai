from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from ..progresso import Progresso

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def parse_data(texto: str | None) -> date | None:
    """Pega a primeira data dd/mm/aaaa do texto."""
    if not texto:
        return None
    m = _DATA.search(texto)
    if not m:
        return None
    d, mth, y = map(int, m.groups())
    try:
        return date(y, mth, d)
    except ValueError:
        return None


@dataclass
class Edital:
    fonte: str
    titulo: str
    url: str
    id_externo: str = ""
    objeto: str = ""
    unidade: str = ""
    uf: str = ""  # estado da fonte (MG, SP, RJ); vem do config.yaml
    situacao: str = ""
    tipo: str = ""
    data_publicacao: date | None = None
    prazo: date | None = None
    texto_extra: str = ""  # texto lido do PDF; usado no filtro, não é salvo inteiro
    relevancia: int = 0
    relevante: bool = False
    do_senai: bool = False

    def __post_init__(self):
        if not self.id_externo:
            base = f"{self.url}|{self.titulo}|{self.objeto}"
            self.id_externo = hashlib.sha1(base.encode()).hexdigest()[:16]

    @property
    def chave(self) -> str:
        return hashlib.sha1(f"{self.fonte}|{self.id_externo}".encode()).hexdigest()

    def texto_busca(self) -> str:
        return " ".join(
            [self.titulo, self.objeto, self.unidade, self.tipo, self.texto_extra]
        )


class Coletor:
    """Cada fonte implementa coletar() e devolve uma lista de Edital."""

    def __init__(self, fonte: dict, config: dict, progresso: Progresso | None = None):
        self.fonte = fonte
        self.nome = fonte["nome"]
        self.url = fonte.get("url", "")
        self.timeout = config.get("coleta", {}).get("timeout_segundos", 60)
        self.config = config
        # sem progresso (ex.: testes), não há tempo limite total
        self.progresso = progresso or Progresso()

    def timeout_ms(self) -> float:
        """Timeout de uma operação de rede, respeitando o tempo limite total."""
        return self.progresso.restante_ms(self.timeout * 1000)

    def coletar(self) -> list[Edital]:
        raise NotImplementedError
