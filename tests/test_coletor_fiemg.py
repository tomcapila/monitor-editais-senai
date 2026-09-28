from datetime import date

from app.coletores.fiemg_paradigma import ColetorFiemgParadigma

HTML = """<!doctype html><html><meta charset="utf-8"><body>
<table>
  <thead><tr><th>Chamamento público</th><th>Linha de fornecimento</th><th>Empresa</th><th>Aprovação</th></tr></thead>
  <tbody><tr><td>CP 001/2026</td><td>Consultoria</td><td>Empresa X Ltda</td><td>10/01/2026</td></tr></tbody>
</table>
<table>
  <thead><tr><th>Código</th><th>Chamamento público</th><th>Unidade compradora</th><th>Objeto</th><th>Encerramento das inscrições</th></tr></thead>
  <tbody>
    <tr><td>12345</td><td>CP 010/2026</td><td>SENAI/DRMG - SEDE</td>
        <td>Credenciamento de consultores</td><td>31/10/2026 17:00</td></tr>
    <tr><td colspan="5">Nenhum registro</td></tr>
  </tbody>
</table>
</body></html>"""


def test_coletor_fiemg_html_local(tmp_path):
    arq = tmp_path / "mural.html"
    arq.write_text(HTML, encoding="utf-8")
    fonte = {"nome": "Teste", "url": arq.as_uri(), "expandir": []}
    editais = ColetorFiemgParadigma(fonte, {"coleta": {"timeout_segundos": 30}}).coletar()

    assert len(editais) == 1
    ed = editais[0]
    assert ed.id_externo == "12345"
    assert ed.titulo == "CP 010/2026"
    assert ed.unidade == "SENAI/DRMG - SEDE"
    assert ed.objeto == "Credenciamento de consultores"
    assert ed.prazo == date(2026, 10, 31)


# Reproduz #tbEditais do portal real (diagnóstico de 27/09/2026): várias colunas
# com display:none no cabeçalho, mas só as visíveis têm <td> nas linhas.
HTML_COLUNAS_OCULTAS = """<!doctype html><html><meta charset="utf-8"><body>
<table>
  <thead><tr>
    <th>Código</th><th style="display:none">Chamamento público</th>
    <th style="display:none">Processo</th><th>Edital</th><th>Unidade compradora</th>
    <th>Objeto</th><th style="display:none">Encerramento das inscrições</th>
    <th>Modalidade</th><th>Processo</th><th>Título</th><th>Situação</th>
  </tr></thead>
  <tbody><tr>
    <td>20646</td><td>SDE 2026004004</td><td>SISTEMA FIEMG</td>
    <td>Consultoria em atendimento ao SENAI/Belo Horizonte</td>
    <td>Processo de seleção sem disputa</td><td>SDE 2026004004</td>
    <td>Não informado</td><td>Habilitado</td>
  </tr></tbody>
</table>
</body></html>"""


def test_coletor_fiemg_ignora_colunas_ocultas(tmp_path):
    arq = tmp_path / "mural.html"
    arq.write_text(HTML_COLUNAS_OCULTAS, encoding="utf-8")
    fonte = {"nome": "Teste", "url": arq.as_uri(), "expandir": []}
    [ed] = ColetorFiemgParadigma(fonte, {"coleta": {"timeout_segundos": 30}}).coletar()

    assert ed.id_externo == "20646"
    assert ed.titulo == "SDE 2026004004"  # "Não informado" no Título é ignorado
    assert ed.unidade == "SISTEMA FIEMG"
    assert ed.objeto.startswith("Consultoria")
    assert ed.tipo == "Processo de seleção sem disputa"
    assert ed.situacao == "Habilitado"
