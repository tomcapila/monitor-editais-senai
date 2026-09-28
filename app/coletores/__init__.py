from ..progresso import Progresso
from .base import Coletor, Edital


def criar_coletor(fonte: dict, config: dict, progresso: Progresso | None = None) -> Coletor:
    """Para adicionar outro estado: crie um módulo novo e registre o tipo aqui."""
    tipo = fonte["tipo"]
    if tipo == "fiemg_api":
        from .fiemg_api import ColetorFiemgApi
        return ColetorFiemgApi(fonte, config, progresso)
    if tipo == "fiemg_paradigma":
        from .fiemg_paradigma import ColetorFiemgParadigma
        return ColetorFiemgParadigma(fonte, config, progresso)
    if tipo == "pagina_links":
        from .pagina_links import ColetorPaginaLinks
        return ColetorPaginaLinks(fonte, config, progresso)
    if tipo == "demo":
        from .demo import ColetorDemo
        return ColetorDemo(fonte, config, progresso)
    raise ValueError(f"Tipo de coletor desconhecido: {tipo}")


__all__ = ["Coletor", "Edital", "criar_coletor"]
