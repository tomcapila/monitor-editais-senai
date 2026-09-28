from ..progresso import Progresso
from .base import Coletor, Edital


def criar_coletor(fonte: dict, config: dict, progresso: Progresso | None = None) -> Coletor:
    """Para adicionar outro estado: crie um módulo novo e registre o tipo aqui."""
    tipo = fonte["tipo"]
    if tipo in ("paradigma_api", "fiemg_api"):  # fiemg_api: nome antigo
        from .paradigma_api import ColetorParadigmaApi
        return ColetorParadigmaApi(fonte, config, progresso)
    if tipo == "fiemg_paradigma":
        from .fiemg_paradigma import ColetorFiemgParadigma
        return ColetorFiemgParadigma(fonte, config, progresso)
    if tipo == "sistema_transparencia":
        from .sistema_transparencia import ColetorSistemaTransparencia
        return ColetorSistemaTransparencia(fonte, config, progresso)
    if tipo == "sebrae_canal":
        from .sebrae_canal import ColetorSebraeCanal
        return ColetorSebraeCanal(fonte, config, progresso)
    if tipo == "sebrae_one":
        from .sebrae_one import ColetorSebraeOne
        return ColetorSebraeOne(fonte, config, progresso)
    if tipo == "sebrae_sgf":
        from .sebrae_sgf import ColetorSebraeSgf
        return ColetorSebraeSgf(fonte, config, progresso)
    if tipo == "pagina_links":
        from .pagina_links import ColetorPaginaLinks
        return ColetorPaginaLinks(fonte, config, progresso)
    if tipo == "demo":
        from .demo import ColetorDemo
        return ColetorDemo(fonte, config, progresso)
    raise ValueError(f"Tipo de coletor desconhecido: {tipo}")


__all__ = ["Coletor", "Edital", "criar_coletor"]
