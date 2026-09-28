import httpx

from app.coleta import resumir_erro


def _erro_http(codigo: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://exemplo.com/")
    resp = httpx.Response(codigo, request=req)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e


def test_resumir_erro():
    # a mensagem original do httpx tem duas linhas e um link da MDN
    assert "\n" in str(_erro_http(403))
    assert resumir_erro(_erro_http(403)) == "o site recusou o acesso (HTTP 403)"
    assert resumir_erro(_erro_http(500)) == "o site respondeu com erro (HTTP 500)"
    assert resumir_erro(httpx.ReadTimeout("x")) == "o site demorou demais para responder"
    assert resumir_erro(httpx.ConnectError("x")) == "não foi possível conectar ao site"
    assert resumir_erro(ValueError("primeira linha\nsegunda")) == "primeira linha"
    assert resumir_erro(ValueError("")) == "ValueError"
