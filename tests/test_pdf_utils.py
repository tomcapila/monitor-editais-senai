from datetime import date

from app.pdf_utils import achar_prazo


def test_achar_prazo():
    texto = (
        "Vigência de 24 meses a partir de 01/01/2026.\n"
        "Período de inscrições: de 01/10/2026 até 31/10/2026.\n"
        "Prazo de vigência 31/12/2028"
    )
    assert achar_prazo(texto) == date(2026, 10, 31)
