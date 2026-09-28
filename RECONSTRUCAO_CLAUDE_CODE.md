# Reconstrução do projeto: Monitor de editais SENAI-MG

Este arquivo é uma instrução para o Claude Code. Ele contém a especificação do projeto e o código-fonte completo de todos os arquivos. Siga as etapas na ordem.

## Contexto

Ferramenta para pesquisar e monitorar editais de credenciamento e contratação de consultoria/instrutoria para pessoa jurídica (CNPJ ativo) nas unidades do SENAI de Minas Gerais.

- Fonte principal: Portal de Compras da FIEMG (plataforma Paradigma), `https://compras.fiemg.com.br/portal/Mural.aspx?nNmTela=E`. O portal atende FIEMG, SESI, SENAI e IEL, e carrega as tabelas via JavaScript. Por isso o coletor usa Playwright.
- Backend: Python 3.10+, FastAPI, APScheduler, SQLite.
- Frontend: um único `static/index.html` servido pelo FastAPI, sem build.
- Alertas: Telegram e e-mail, opcionais, configurados por `.env`.
- Idioma do código, comentários e interface: português do Brasil.

## Estado atual (importante)

- Testado: coleta com a fonte `demo`, filtro, banco, API, painel, e o coletor Playwright contra uma página HTML local que imita o portal.
- **Não testado:** acesso ao portal real da FIEMG. O mapeamento de colunas (`MAPA_COLUNAS` em `app/coletores/fiemg_paradigma.py`) é uma suposição baseada nos cabeçalhos visíveis no portal e provavelmente precisa de ajuste.

## Etapa 1: recriar os arquivos

Crie exatamente os arquivos listados na seção "Código-fonte", com o conteúdo indicado. Não altere o código nesta etapa. `app/__init__.py` é um arquivo vazio.

Estrutura esperada:

```
monitor-editais-senai/
├── .env.example
├── README.md
├── config.yaml
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── alertas.py
│   ├── coleta.py
│   ├── config.py
│   ├── db.py
│   ├── diagnostico.py
│   ├── filtro.py
│   ├── main.py
│   ├── pdf_utils.py
│   └── coletores/
│       ├── __init__.py
│       ├── base.py
│       ├── demo.py
│       ├── fiemg_paradigma.py
│       └── pagina_links.py
├── scripts/
│   └── diagnostico_fiemg.py
└── static/
    └── index.html
```

Crie também um `.gitignore` com: `.venv/`, `__pycache__/`, `.env`, `editais.db`, `diagnostico/`.

## Etapa 2: instalar e validar sem internet

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
```

Validação com dados de exemplo (não altere o `config.yaml` do repositório; use uma cópia temporária ou reverta depois):

1. No `config.yaml`, deixe apenas a fonte `demo` com `ativo: true`.
2. Rode `python -m app.coleta`. Esperado: `encontrados: 3, novos: 3, erros: []`.
3. Suba `uvicorn app.main:app --port 8000` e confira:
   - `GET /api/editais` retorna 2 itens (o de "Aquisição de equipamentos" é descartado pelo filtro).
   - `GET /api/editais?relevantes=false&abertos=false` retorna 3.
   - `GET /api/status` mostra a última execução.
   - `GET /` retorna 200.
4. Teste o coletor Playwright contra um HTML local com duas tabelas: uma com cabeçalhos `Chamamento público | Linha de fornecimento | Empresa | Aprovação` (deve ser ignorada) e outra com `Código | Chamamento público | Unidade compradora | Objeto | Encerramento das inscrições` (deve gerar um Edital com prazo lido corretamente). Uma linha com `Nenhum registro` em `colspan` deve ser ignorada.
5. Teste `achar_prazo` com o texto: `"Vigência de 24 meses a partir de 01/01/2026.\nPeríodo de inscrições: de 01/10/2026 até 31/10/2026.\nPrazo de vigência 31/12/2028"`. Esperado: `2026-10-31`.
6. Restaure o `config.yaml` original e apague `editais.db`.

Se quiser, transforme os testes 2 a 5 em testes `pytest` dentro de `tests/`.

## Etapa 3: validar contra o portal real

Pode falhar se o ambiente não tiver acesso de rede a `compras.fiemg.com.br`. Nesse caso, informe e pare aqui.

1. Rode o diagnóstico sem janela: `python -c "from app.diagnostico import rodar; import json; r = rodar(); print(r['status'], r.get('erro'))"`.
2. Leia `diagnostico/tabelas.json` e `diagnostico/rede.json`.
3. Compare os cabeçalhos reais com `MAPA_COLUNAS` e `CABECALHOS_IGNORAR` em `app/coletores/fiemg_paradigma.py`. Ajuste o que não bater.
4. Verifique se os textos em `expandir` (config.yaml) existem na página. Ajuste se necessário.
5. Se `rede.json` mostrar uma chamada que devolve JSON com a lista de processos, proponha (sem implementar sem autorização) um coletor alternativo com `httpx` chamando esse endpoint direto.
6. Ative só a fonte `fiemg_paradigma`, apague `editais.db` e rode `python -m app.coleta`. Relate quantos editais foram encontrados, quantos relevantes e quantos marcados como SENAI.

## Regras

- Não invente endpoints, seletores ou cabeçalhos: confirme no diagnóstico.
- Mantenha frequência baixa de acesso ao portal (nada de loops rápidos de teste).
- Não commite `.env`, `editais.db` nem a pasta `diagnostico/`.
- Ao final, faça um resumo do que funcionou, do que foi ajustado e do que ficou pendente.

## Código-fonte


### `requirements.txt`

````text
fastapi>=0.110
uvicorn[standard]>=0.29
apscheduler>=3.10,<4
playwright>=1.44
httpx>=0.27
beautifulsoup4>=4.12
pdfplumber>=0.11
pyyaml>=6.0
python-dotenv>=1.0
````

### `config.yaml`

````yaml
# Configuração do monitor de editais SENAI-MG
# Edite este arquivo para mudar fontes, palavras-chave e frequência.

coleta:
  intervalo_horas: 12        # frequência da coleta automática
  timeout_segundos: 60
  ler_pdfs: true             # baixa PDFs encontrados e lê as primeiras páginas
  max_paginas_pdf: 5

filtro:
  # Termos que indicam que o edital é para consultoria/instrutoria PJ.
  # Escreva sem acento e em minúsculas; o texto é normalizado antes da comparação.
  termos_relevantes:
    - credenciamento
    - chamamento publico
    - consultoria
    - consultor
    - instrutoria
    - instrutor
    - pessoa juridica
    - pessoas juridicas
    - cadastro de consultores
    - prestacao de servicos tecnicos
  # Se algum destes aparecer, o edital é descartado como irrelevante.
  termos_excluir:
    - aquisicao de equipamentos
    - material de consumo
    - obra de engenharia
    - generos alimenticios
  # Quantos termos relevantes distintos precisam aparecer.
  relevancia_minima: 1
  # Usado para marcar o que é do SENAI (o portal da FIEMG mistura SESI, IEL etc.)
  termos_orgao:
    - senai

fontes:
  - tipo: fiemg_paradigma
    nome: Portal de Compras FIEMG
    url: https://compras.fiemg.com.br/portal/Mural.aspx?nNmTela=E
    ativo: true
    # Textos de links que o coletor tenta clicar para carregar listas completas.
    # Ajuste depois de rodar scripts/diagnostico_fiemg.py.
    expandir:
      - Ver todos os editais de cadastro em andamento
      - Ver todas as negociações em andamento

  - tipo: pagina_links
    nome: FIEMG credenciamento de consultores (IEL)
    url: https://www.fiemg.com.br/area-de-interesse/capacitacao-empresarial/credenciamento-de-consultores/
    ativo: false             # ative se quiser acompanhar também o IEL-MG
    unidade: IEL-MG

  - tipo: demo
    nome: Dados de exemplo
    ativo: false             # ative só para testar a interface sem internet

alertas:
  telegram: false            # requer TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env
  email: false               # requer variáveis SMTP_* no .env
````

### `.env.example`

````bash
# Copie para .env e preencha só o que for usar.

# Telegram: crie um bot com @BotFather e pegue o chat_id com @userinfobot
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

# E-mail (ex.: Gmail com senha de app)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
EMAIL_PARA=
````

### `README.md`

````markdown
# Monitor de editais SENAI-MG (MVP)

Coleta editais e chamamentos públicos do Portal de Compras da FIEMG,
filtra os que interessam para consultoria/instrutoria PJ, guarda num SQLite,
mostra num painel HTML e avisa por Telegram ou e-mail quando surge algo novo.

## Estrutura

```
config.yaml                  fontes, palavras-chave, frequência, alertas
.env.example                 credenciais de alerta (copie para .env)
app/
  main.py                    servidor FastAPI + agendador
  coleta.py                  orquestra: coleta > PDF > filtro > banco > alerta
  filtro.py                  pontuação por palavras-chave
  pdf_utils.py               baixa PDF, extrai texto, tenta achar o prazo
  db.py                      SQLite
  alertas.py                 Telegram e e-mail
  diagnostico.py             inspeciona o portal real (usado pelo painel e pelo script)
  coletores/
    base.py                  modelo Edital + classe base
    fiemg_paradigma.py       Portal de Compras FIEMG (Playwright)
    pagina_links.py          páginas simples com links/PDFs (modelo p/ outros estados)
    demo.py                  dados fictícios para testar a interface
static/index.html            painel
scripts/diagnostico_fiemg.py diagnóstico pelo terminal (navegador visível)
```

## Instalação

Requer Python 3.10 ou mais novo.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env        # Windows: copy .env.example .env
```

## Primeiro uso (nesta ordem)

1. **Teste a interface sem internet.** No `config.yaml`, deixe só a fonte `demo`
   com `ativo: true`. Rode `python -m app.coleta` e depois
   `uvicorn app.main:app --reload`. Abra http://localhost:8000.

2. **Diagnostique o portal real.** No painel, abra "Diagnóstico do portal" no
   fim da página e clique em "Rodar diagnóstico". Ou, pelo terminal, rode
   `python scripts/diagnostico_fiemg.py` para ver o navegador aberto. Ambos salvam as tabelas em `diagnostico/tabelas.json` e as
   chamadas AJAX em `diagnostico/rede.json`. Confira se os cabeçalhos batem com
   `MAPA_COLUNAS` em `app/coletores/fiemg_paradigma.py` e ajuste se preciso.

3. **Ative a fonte real.** Volte `demo` para `ativo: false`, `fiemg_paradigma`
   para `ativo: true`, apague `editais.db` e rode a coleta de novo.

A primeira coleta real não dispara alertas (senão tudo viraria "novo").
A partir da segunda, só o que for novo e relevante gera aviso.

## Coleta automática

Com o servidor rodando, a coleta acontece a cada `intervalo_horas`.
Se preferir sem servidor, agende `python -m app.coleta` no cron (Linux)
ou no Agendador de Tarefas (Windows).

## Limitações conhecidas

- O coletor da FIEMG **não foi validado contra o site real**. O portal carrega
  as tabelas por JavaScript e a estrutura exata pode diferir. O passo 2 existe
  para isso.
- Se `rede.json` mostrar que as tabelas vêm de uma chamada que devolve JSON,
  vale trocar o Playwright por uma requisição direta com `httpx`: fica mais
  rápido e mais estável.
- A detecção de prazo em PDF é heurística. Confira sempre no edital.
- Mudanças no layout do portal quebram o coletor. Fique de olho nos erros
  mostrados no topo do painel.
- Mantenha frequência baixa de acesso e respeite os termos de uso do portal.

## Adicionar outro estado

Crie um módulo em `app/coletores/` herdando de `Coletor`, devolva uma lista de
`Edital` em `coletar()`, registre o tipo em `app/coletores/__init__.py` e
adicione a fonte no `config.yaml`. Para sites simples, `pagina_links` já pode
servir sem código novo.
````

### `app/__init__.py`

*(arquivo vazio)*

### `app/config.py`

````python
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "editais.db"
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")


def carregar_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
````

### `app/coletores/__init__.py`

````python
from .base import Coletor, Edital


def criar_coletor(fonte: dict, config: dict) -> Coletor:
    """Para adicionar outro estado: crie um módulo novo e registre o tipo aqui."""
    tipo = fonte["tipo"]
    if tipo == "fiemg_paradigma":
        from .fiemg_paradigma import ColetorFiemgParadigma
        return ColetorFiemgParadigma(fonte, config)
    if tipo == "pagina_links":
        from .pagina_links import ColetorPaginaLinks
        return ColetorPaginaLinks(fonte, config)
    if tipo == "demo":
        from .demo import ColetorDemo
        return ColetorDemo(fonte, config)
    raise ValueError(f"Tipo de coletor desconhecido: {tipo}")


__all__ = ["Coletor", "Edital", "criar_coletor"]
````

### `app/coletores/base.py`

````python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

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

    def __init__(self, fonte: dict, config: dict):
        self.fonte = fonte
        self.nome = fonte["nome"]
        self.url = fonte.get("url", "")
        self.timeout = config.get("coleta", {}).get("timeout_segundos", 60)
        self.config = config

    def coletar(self) -> list[Edital]:
        raise NotImplementedError
````

### `app/coletores/fiemg_paradigma.py`

````python
"""
Coletor do Portal de Compras da FIEMG (plataforma Paradigma).

O portal carrega as tabelas via JavaScript, por isso usamos Playwright
(navegador real, sem janela). A estratégia é genérica: renderiza a página,
lê todas as tabelas e mapeia as colunas pelo texto do cabeçalho.

ATENÇÃO: este coletor não foi testado contra o site real. Rode
scripts/diagnostico_fiemg.py primeiro e ajuste MAPA_COLUNAS e 'expandir'
no config.yaml conforme o que aparecer.
"""
from __future__ import annotations

import logging
import unicodedata

from playwright.sync_api import sync_playwright

from .base import USER_AGENT, Coletor, Edital, parse_data

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


# Cabeçalho normalizado -> campo do Edital. A primeira coluna não vazia vence.
MAPA_COLUNAS = {
    "id_externo": ["codigo", "processo", "numero", "edital", "rfi"],
    "titulo": ["chamamento publico", "titulo", "edital"],
    "objeto": ["objeto"],
    "unidade": ["unidade compradora"],
    "tipo": ["modalidade", "tipo", "linha de fornecimento"],
    "situacao": ["situacao"],
    "prazo": ["encerramento das inscricoes", "encerra em", "data/hora final"],
    "data_publicacao": ["inicio das inscricoes", "data/hora inicial"],
}

# Tabelas com estes cabeçalhos listam empresas já credenciadas, não editais.
CABECALHOS_IGNORAR = {"empresa", "aprovacao"}

JS_TABELAS = """
els => els.map(t => {
  let headers = [...t.querySelectorAll('thead th')].map(h => h.innerText.trim());
  let linhas = [...t.querySelectorAll('tbody tr')];
  if (!headers.length) {
    const primeira = t.querySelector('tr');
    if (primeira) headers = [...primeira.querySelectorAll('th')].map(h => h.innerText.trim());
  }
  return {
    headers,
    rows: linhas.map(tr => ({
      cells: [...tr.querySelectorAll('td')].map(td => td.innerText.trim()),
      links: [...tr.querySelectorAll('a[href]')]
               .map(a => a.href)
               .filter(h => h && !h.startsWith('javascript')),
    })),
  };
})
"""


class ColetorFiemgParadigma(Coletor):
    def coletar(self) -> list[Edital]:
        resultados: dict[str, Edital] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="pt-BR", user_agent=USER_AGENT)
            try:
                # 1) página inicial do mural
                self._abrir(page)
                for ed in self._extrair(page):
                    resultados[ed.chave] = ed

                # 2) listas completas ("Ver todos...")
                for texto in self.fonte.get("expandir", []):
                    try:
                        self._abrir(page)
                        link = page.get_by_text(texto, exact=False).first
                        link.click(timeout=5000)
                        page.wait_for_load_state("networkidle", timeout=self.timeout * 1000)
                        page.wait_for_timeout(1500)
                        for ed in self._extrair(page):
                            resultados[ed.chave] = ed
                    except Exception as e:  # link pode não existir ou mudar
                        log.warning("Não consegui expandir '%s': %s", texto, e)
            finally:
                browser.close()
        return list(resultados.values())

    def _abrir(self, page):
        page.goto(self.url, wait_until="networkidle", timeout=self.timeout * 1000)
        # as tabelas chegam por AJAX depois do carregamento
        page.wait_for_timeout(2000)

    def _extrair(self, page) -> list[Edital]:
        tabelas = page.eval_on_selector_all("table", JS_TABELAS)
        editais = []
        for tab in tabelas:
            headers = [_norm(h) for h in tab["headers"]]
            if not headers or CABECALHOS_IGNORAR.issubset(set(headers)):
                continue
            if not any(h in ("objeto", "chamamento publico") for h in headers):
                continue
            for row in tab["rows"]:
                ed = self._linha_para_edital(headers, row)
                if ed:
                    editais.append(ed)
        return editais

    def _linha_para_edital(self, headers: list[str], row: dict) -> Edital | None:
        cells = row["cells"]
        if len(cells) < 2:
            return None

        def campo(nome: str) -> str:
            for alvo in MAPA_COLUNAS[nome]:
                for i, h in enumerate(headers):
                    if h == alvo and i < len(cells) and cells[i]:
                        return cells[i]
            return ""

        objeto = campo("objeto")
        titulo = campo("titulo") or objeto[:140]
        if not titulo:
            return None

        return Edital(
            fonte=self.nome,
            titulo=titulo,
            objeto=objeto,
            url=(row["links"][0] if row["links"] else self.url),
            id_externo=campo("id_externo"),
            unidade=campo("unidade"),
            tipo=campo("tipo"),
            situacao=campo("situacao"),
            prazo=parse_data(campo("prazo")),
            data_publicacao=parse_data(campo("data_publicacao")),
        )
````

### `app/coletores/pagina_links.py`

````python
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
        r = httpx.get(
            self.url,
            timeout=self.timeout,
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
````

### `app/coletores/demo.py`

````python
"""Dados fictícios para testar a interface sem acessar a internet."""
from __future__ import annotations

from datetime import date, timedelta

from .base import Coletor, Edital


class ColetorDemo(Coletor):
    def coletar(self) -> list[Edital]:
        hoje = date.today()
        return [
            Edital(
                fonte=self.nome,
                id_externo="demo-1",
                titulo="[EXEMPLO] Credenciamento de pessoas jurídicas para consultoria em gestão",
                objeto="Cadastro de consultores para atendimento às unidades do SENAI em Minas Gerais",
                unidade="SENAI/DRMG - SEDE",
                tipo="Chamamento público",
                url="https://example.com/demo-1",
                prazo=hoje + timedelta(days=2),
            ),
            Edital(
                fonte=self.nome,
                id_externo="demo-2",
                titulo="[EXEMPLO] Chamamento público para instrutoria em segurança do trabalho",
                objeto="Instrutoria para cursos de NR-10 e NR-35",
                unidade="SENAI/DRMG - CFP AFONSO GRECO",
                tipo="Chamamento público",
                url="https://example.com/demo-2",
                prazo=hoje + timedelta(days=21),
            ),
            Edital(
                fonte=self.nome,
                id_externo="demo-3",
                titulo="[EXEMPLO] Aquisição de equipamentos de informática",
                objeto="Registro de preços de notebooks",
                unidade="SESI/DRMG - SEDE",
                tipo="Pregão eletrônico",
                url="https://example.com/demo-3",
                prazo=hoje + timedelta(days=9),
            ),
        ]
````

### `app/filtro.py`

````python
from __future__ import annotations

import unicodedata

from .coletores.base import Edital


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.lower().split())


def avaliar(ed: Edital, cfg: dict) -> Edital:
    """Preenche relevancia, relevante e do_senai a partir do config."""
    texto = normalizar(ed.texto_busca())

    if any(normalizar(t) in texto for t in cfg.get("termos_excluir", [])):
        ed.relevancia = 0
    else:
        ed.relevancia = sum(
            1 for t in cfg.get("termos_relevantes", []) if normalizar(t) in texto
        )
    ed.relevante = ed.relevancia >= cfg.get("relevancia_minima", 1)
    ed.do_senai = any(normalizar(t) in texto for t in cfg.get("termos_orgao", []))
    return ed
````

### `app/pdf_utils.py`

````python
from __future__ import annotations

import io
import logging
import re
from datetime import date

import httpx
import pdfplumber

from .coletores.base import USER_AGENT, parse_data

log = logging.getLogger(__name__)

# Heurística: data que aparece perto de palavras ligadas a prazo de inscrição.
_PRAZO = re.compile(
    r"(inscri[cç][aãoõ]\w*|propostas?|encerramento)([^\n]{0,160})",
    re.IGNORECASE,
)
_DATAS = re.compile(r"\d{2}/\d{2}/\d{4}")


def extrair_texto_pdf(url: str, max_paginas: int = 5, timeout: int = 60) -> str:
    """Baixa o PDF e devolve o texto das primeiras páginas ('' se não for PDF)."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        if b"%PDF" not in r.content[:1024]:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_paginas])
    except Exception as e:
        log.warning("Falha ao ler PDF %s: %s", url, e)
        return ""


def achar_prazo(texto: str) -> date | None:
    """Tenta achar o prazo de inscrição. É heurístico: confira no edital."""
    datas = [
        parse_data(d)
        for m in _PRAZO.finditer(texto)
        for d in _DATAS.findall(m.group(2))
    ]
    datas = [d for d in datas if d]
    return max(datas) if datas else None
````

### `app/db.py`

````python
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH
from .coletores.base import Edital

SCHEMA = """
CREATE TABLE IF NOT EXISTS editais (
    chave TEXT PRIMARY KEY,
    fonte TEXT, id_externo TEXT, titulo TEXT, objeto TEXT, unidade TEXT,
    url TEXT, situacao TEXT, tipo TEXT,
    data_publicacao TEXT, prazo TEXT,
    relevancia INTEGER, relevante INTEGER, do_senai INTEGER,
    trecho_pdf TEXT,
    primeiro_visto TEXT, ultimo_visto TEXT,
    notificado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT, fim TEXT, encontrados INTEGER, novos INTEGER, erros TEXT
);
"""


@contextmanager
def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conectar() as con:
        con.executescript(SCHEMA)


def vazio() -> bool:
    with conectar() as con:
        return con.execute("SELECT COUNT(*) FROM editais").fetchone()[0] == 0


def existe(chave: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM editais WHERE chave = ?", (chave,)).fetchone() is not None


def salvar(ed: Edital) -> bool:
    """Insere ou atualiza. Devolve True se o edital é novo."""
    agora = datetime.now().isoformat(timespec="seconds")
    dados = {
        "chave": ed.chave, "fonte": ed.fonte, "id_externo": ed.id_externo,
        "titulo": ed.titulo, "objeto": ed.objeto, "unidade": ed.unidade,
        "url": ed.url, "situacao": ed.situacao, "tipo": ed.tipo,
        "data_publicacao": ed.data_publicacao.isoformat() if ed.data_publicacao else None,
        "prazo": ed.prazo.isoformat() if ed.prazo else None,
        "relevancia": ed.relevancia, "relevante": int(ed.relevante),
        "do_senai": int(ed.do_senai), "trecho_pdf": ed.texto_extra[:1500] or None,
        "agora": agora,
    }
    with conectar() as con:
        existe = con.execute(
            "SELECT 1 FROM editais WHERE chave = ?", (ed.chave,)
        ).fetchone()
        if existe:
            con.execute(
                """UPDATE editais SET titulo=:titulo, objeto=:objeto, unidade=:unidade,
                   url=:url, situacao=:situacao, tipo=:tipo, prazo=COALESCE(:prazo, prazo),
                   relevancia=:relevancia, relevante=:relevante, do_senai=:do_senai,
                   trecho_pdf=COALESCE(:trecho_pdf, trecho_pdf), ultimo_visto=:agora
                   WHERE chave=:chave""",
                dados,
            )
            return False
        con.execute(
            """INSERT INTO editais (chave, fonte, id_externo, titulo, objeto, unidade,
               url, situacao, tipo, data_publicacao, prazo, relevancia, relevante,
               do_senai, trecho_pdf, primeiro_visto, ultimo_visto)
               VALUES (:chave, :fonte, :id_externo, :titulo, :objeto, :unidade,
               :url, :situacao, :tipo, :data_publicacao, :prazo, :relevancia, :relevante,
               :do_senai, :trecho_pdf, :agora, :agora)""",
            dados,
        )
        return True


def marcar_notificados(chaves: list[str]):
    with conectar() as con:
        con.executemany(
            "UPDATE editais SET notificado = 1 WHERE chave = ?", [(c,) for c in chaves]
        )


def listar(q: str = "", apenas_relevantes=False, apenas_abertos=False,
           apenas_senai=False, limite: int = 500) -> list[dict]:
    where, params = [], []
    if q:
        where.append("(titulo || ' ' || COALESCE(objeto,'') || ' ' || COALESCE(unidade,'')) LIKE ?")
        params.append(f"%{q}%")
    if apenas_relevantes:
        where.append("relevante = 1")
    if apenas_abertos:
        where.append("(prazo IS NULL OR prazo >= date('now', 'localtime'))")
    if apenas_senai:
        where.append("do_senai = 1")
    sql = "SELECT * FROM editais"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += """ ORDER BY CASE
                 WHEN prazo IS NULL THEN 1
                 WHEN prazo < date('now', 'localtime') THEN 2
                 ELSE 0 END,
               prazo, primeiro_visto DESC LIMIT ?"""
    params.append(limite)
    with conectar() as con:
        return [dict(r) for r in con.execute(sql, params)]


def registrar_execucao(inicio: str, fim: str, encontrados: int, novos: int, erros: list[str]):
    with conectar() as con:
        con.execute(
            "INSERT INTO execucoes (inicio, fim, encontrados, novos, erros) VALUES (?,?,?,?,?)",
            (inicio, fim, encontrados, novos, "\n".join(erros) or None),
        )


def ultima_execucao() -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM execucoes ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None
````

### `app/alertas.py`

````python
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx

from .coletores.base import Edital

log = logging.getLogger(__name__)


def _resumo(editais: list[Edital]) -> str:
    linhas = [f"{len(editais)} edital(is) novo(s) relevante(s):", ""]
    for ed in editais[:20]:
        prazo = ed.prazo.strftime("%d/%m/%Y") if ed.prazo else "prazo não identificado"
        linhas += [f"• {ed.titulo}", f"  {ed.unidade or ed.fonte} | {prazo}", f"  {ed.url}", ""]
    if len(editais) > 20:
        linhas.append(f"... e mais {len(editais) - 20}. Veja no painel.")
    return "\n".join(linhas)


def enviar(editais: list[Edital], cfg: dict) -> bool:
    """Devolve True se ao menos um canal enviou com sucesso."""
    if not editais:
        return False
    texto, ok = _resumo(editais), False

    if cfg.get("telegram"):
        token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            try:
                r = httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": texto[:4000],
                          "disable_web_page_preview": True},
                    timeout=30,
                )
                r.raise_for_status()
                ok = True
            except Exception as e:
                log.error("Falha no Telegram: %s", e)
        else:
            log.warning("Telegram ativado mas TELEGRAM_TOKEN/CHAT_ID não definidos")

    if cfg.get("email"):
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[Editais SENAI-MG] {len(editais)} novo(s)"
            msg["From"] = os.environ["SMTP_USER"]
            msg["To"] = os.environ["EMAIL_PARA"]
            msg.set_content(texto)
            with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"),
                              int(os.getenv("SMTP_PORT", "587"))) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                s.send_message(msg)
            ok = True
        except Exception as e:
            log.error("Falha no e-mail: %s", e)

    return ok
````

### `app/coleta.py`

````python
"""
Roda todas as fontes ativas, filtra, salva e alerta.
Também pode ser executado direto:  python -m app.coleta
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from . import alertas, db
from .coletores import criar_coletor
from .config import carregar_config
from .filtro import avaliar
from .pdf_utils import achar_prazo, extrair_texto_pdf

log = logging.getLogger(__name__)

_lock = threading.Lock()
estado = {"rodando": False, "inicio": None}


def executar_coleta() -> dict:
    if not _lock.acquire(blocking=False):
        return {"status": "ja_rodando"}
    config = carregar_config()
    inicio = datetime.now().isoformat(timespec="seconds")
    estado.update(rodando=True, inicio=inicio)
    encontrados, novos, erros, para_alertar = 0, 0, [], []
    try:
        db.iniciar()
        primeira_vez = db.vazio()  # não dispara alerta em massa na 1ª coleta
        opts = config.get("coleta", {})

        for fonte in config.get("fontes", []):
            if not fonte.get("ativo", True):
                continue
            log.info("Coletando: %s", fonte["nome"])
            try:
                editais = criar_coletor(fonte, config).coletar()
            except Exception as e:
                log.exception("Erro na fonte %s", fonte["nome"])
                erros.append(f"{fonte['nome']}: {e}")
                continue

            for ed in editais:
                encontrados += 1
                eh_pdf = ed.url.lower().split("?")[0].endswith(".pdf")
                if opts.get("ler_pdfs") and eh_pdf and not db.existe(ed.chave):
                    ed.texto_extra = extrair_texto_pdf(
                        ed.url, opts.get("max_paginas_pdf", 5), opts.get("timeout_segundos", 60)
                    )
                    ed.prazo = ed.prazo or achar_prazo(ed.texto_extra)
                avaliar(ed, config.get("filtro", {}))
                if db.salvar(ed):
                    novos += 1
                    if ed.relevante and not primeira_vez:
                        para_alertar.append(ed)

        if para_alertar and alertas.enviar(para_alertar, config.get("alertas", {})):
            db.marcar_notificados([e.chave for e in para_alertar])
    finally:
        fim = datetime.now().isoformat(timespec="seconds")
        db.registrar_execucao(inicio, fim, encontrados, novos, erros)
        estado.update(rodando=False)
        _lock.release()

    resultado = {"status": "ok", "encontrados": encontrados, "novos": novos,
                 "alertados": len(para_alertar), "erros": erros}
    log.info("Coleta concluída: %s", resultado)
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(executar_coleta())
````

### `app/diagnostico.py`

````python
"""
Diagnóstico do Portal de Compras FIEMG.

Pode rodar de dois jeitos:
  - pelo painel (botão "Rodar diagnóstico"), sem janela;
  - pelo terminal: python scripts/diagnostico_fiemg.py (com janela visível).

Salva em diagnostico/: pagina.html, tela.png, tabelas.json, rede.json.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

from playwright.sync_api import sync_playwright

from .config import BASE_DIR

URL_PADRAO = "https://compras.fiemg.com.br/portal/Mural.aspx?nNmTela=E"
SAIDA = BASE_DIR / "diagnostico"

JS = """
els => els.map((t, i) => ({
  indice: i,
  id: t.id,
  headers: [...t.querySelectorAll('th')].map(h => h.innerText.trim()),
  linhas: [...t.querySelectorAll('tbody tr')].slice(0, 3)
           .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
  total_linhas: t.querySelectorAll('tbody tr').length,
}))
"""

_lock = threading.Lock()
estado = {"rodando": False, "erro": None}


def rodar(url: str = URL_PADRAO, visivel: bool = False, pausa=None) -> dict:
    """Executa o diagnóstico e devolve o resumo. 'pausa' é chamada antes de fechar."""
    if not _lock.acquire(blocking=False):
        return {"status": "ja_rodando"}
    estado.update(rodando=True, erro=None)
    SAIDA.mkdir(exist_ok=True)
    chamadas = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not visivel)
            page = browser.new_page(locale="pt-BR")

            def registrar(resp):
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                item = {"url": resp.url, "metodo": resp.request.method,
                        "status": resp.status,
                        "tipo": resp.headers.get("content-type", ""),
                        "post": resp.request.post_data}
                try:
                    item["amostra"] = resp.text()[:800]
                except Exception:
                    pass
                chamadas.append(item)

            page.on("response", registrar)
            page.goto(url, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(4000)

            (SAIDA / "pagina.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(SAIDA / "tela.png"), full_page=True)
            tabelas = page.eval_on_selector_all("table", JS)
            if pausa:
                pausa()
            browser.close()

        resumo = {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "url": url,
            "tabelas": tabelas,
            "rede": chamadas,
        }
        (SAIDA / "tabelas.json").write_text(
            json.dumps(tabelas, ensure_ascii=False, indent=2), encoding="utf-8")
        (SAIDA / "rede.json").write_text(
            json.dumps(chamadas, ensure_ascii=False, indent=2), encoding="utf-8")
        (SAIDA / "resumo.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", **resumo}
    except Exception as e:
        estado["erro"] = str(e)
        return {"status": "erro", "erro": str(e)}
    finally:
        estado["rodando"] = False
        _lock.release()


def ultimo_resultado() -> dict | None:
    arq = SAIDA / "resumo.json"
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))
````

### `app/main.py`

````python
"""
Servidor do painel.  Rodar com:  uvicorn app.main:app --reload
Depois abra http://localhost:8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, diagnostico
from .coleta import estado, executar_coleta
from .config import STATIC_DIR, carregar_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
agendador = BackgroundScheduler(timezone="America/Sao_Paulo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.iniciar()
    horas = carregar_config().get("coleta", {}).get("intervalo_horas", 12)
    agendador.add_job(executar_coleta, "interval", hours=horas, id="coleta",
                      max_instances=1, coalesce=True)
    agendador.start()
    yield
    agendador.shutdown(wait=False)


app = FastAPI(title="Monitor de editais SENAI-MG", lifespan=lifespan)
diagnostico.SAIDA.mkdir(exist_ok=True)
app.mount("/diagnostico-arquivos", StaticFiles(directory=diagnostico.SAIDA), name="diag")


@app.get("/")
def pagina():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/editais")
def api_editais(q: str = "", relevantes: bool = True, abertos: bool = True,
                senai: bool = False):
    return db.listar(q, relevantes, abertos, senai)


@app.post("/api/coletar")
def api_coletar(tarefas: BackgroundTasks):
    if estado["rodando"]:
        return {"status": "ja_rodando"}
    tarefas.add_task(executar_coleta)
    return {"status": "iniciada"}


@app.get("/api/status")
def api_status():
    job = agendador.get_job("coleta")
    return {
        "rodando": estado["rodando"],
        "ultima": db.ultima_execucao(),
        "proxima": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


@app.post("/api/diagnostico")
def api_rodar_diagnostico(tarefas: BackgroundTasks):
    if diagnostico.estado["rodando"]:
        return {"status": "ja_rodando"}
    tarefas.add_task(diagnostico.rodar)
    return {"status": "iniciado"}


@app.get("/api/diagnostico")
def api_ver_diagnostico():
    return {
        "rodando": diagnostico.estado["rodando"],
        "erro": diagnostico.estado["erro"],
        "resultado": diagnostico.ultimo_resultado(),
    }
````

### `scripts/diagnostico_fiemg.py`

````python
"""
Diagnóstico pelo terminal, com navegador visível.
Também dá para rodar pelo painel (botão "Rodar diagnóstico").

    python scripts/diagnostico_fiemg.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.diagnostico import rodar  # noqa: E402

r = rodar(visivel=True, pausa=lambda: input("Navegue à vontade. Enter para fechar..."))
if r["status"] != "ok":
    print("Falhou:", r.get("erro"))
    sys.exit(1)
print(f"{len(r['tabelas'])} tabelas encontradas:")
for t in r["tabelas"]:
    print(f"  #{t['indice']} ({t['total_linhas']} linhas): {t['headers'][:8]}")
print(f"{len(r['rede'])} chamadas AJAX. Arquivos salvos em diagnostico/")
````

### `static/index.html`

````html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Editais SENAI-MG</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --fundo: #F4F6F8;
    --papel: #FFFFFF;
    --tinta: #18212F;
    --tinta-2: #556070;
    --linha: #DDE2E8;
    --aco: #2F4B7C;
    --ambar: #B7791F;
    --carmim: #A23B3B;
    --musgo: #3D6B50;
    --fonte: "Public Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--fundo); color: var(--tinta);
    font-family: var(--fonte); font-size: 16px; line-height: 1.5;
  }
  .wrap { max-width: 1040px; margin: 0 auto; padding: 32px 20px 64px; }

  header { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;
           justify-content: space-between; margin-bottom: 28px; }
  h1 { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; margin: 0; line-height: 1.1; }
  .status { color: var(--tinta-2); font-size: .875rem; margin-top: 6px; }
  .status.erro { color: var(--carmim); }

  button {
    font: inherit; font-weight: 600; font-size: .9375rem; cursor: pointer;
    background: var(--aco); color: #fff; border: 0; border-radius: 6px; padding: 10px 18px;
  }
  button:disabled { opacity: .55; cursor: progress; }
  button:focus-visible, input:focus-visible, a:focus-visible, label:focus-within {
    outline: 3px solid color-mix(in srgb, var(--aco) 45%, transparent); outline-offset: 2px;
  }

  .filtros { display: flex; flex-wrap: wrap; gap: 10px 20px; align-items: center;
             padding: 14px 0; border-top: 2px solid var(--tinta); border-bottom: 1px solid var(--linha); }
  .filtros input[type=search] {
    flex: 1 1 260px; font: inherit; padding: 9px 12px; border: 1px solid var(--linha);
    border-radius: 6px; background: var(--papel); color: var(--tinta);
  }
  .filtros label { display: inline-flex; gap: 6px; align-items: center; font-size: .9375rem;
                   color: var(--tinta-2); cursor: pointer; border-radius: 4px; }
  .filtros input[type=checkbox] { accent-color: var(--aco); width: 16px; height: 16px; }
  .contagem { margin-left: auto; font-size: .875rem; color: var(--tinta-2); }

  ol { list-style: none; margin: 0; padding: 0; }
  li.edital {
    display: grid; grid-template-columns: 92px 1fr auto; gap: 20px; align-items: start;
    padding: 20px 0; border-bottom: 1px solid var(--linha);
  }
  .prazo { text-align: right; font-variant-numeric: tabular-nums; }
  .prazo b { display: block; font-size: 2.5rem; font-weight: 800; line-height: 1; letter-spacing: -0.03em; }
  .prazo span { font-size: .8125rem; color: var(--tinta-2); }
  .prazo.urgente b { color: var(--carmim); }
  .prazo.perto b { color: var(--ambar); }
  .prazo.folga b { color: var(--aco); }
  .prazo.encerrado b, .prazo.sem b { color: var(--linha); font-size: 1.75rem; padding-top: 6px; }

  .corpo h2 { font-size: 1.0625rem; font-weight: 600; margin: 0 0 4px; line-height: 1.35; max-width: 70ch; }
  .corpo p { margin: 0 0 8px; color: var(--tinta-2); font-size: .9375rem; max-width: 72ch;
             display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .8125rem; color: var(--tinta-2); }
  .novo { color: var(--musgo); font-weight: 700; }
  .data { color: var(--tinta); }

  a.abrir { color: var(--aco); font-weight: 600; font-size: .9375rem; text-decoration: none;
            white-space: nowrap; padding-top: 2px; }
  a.abrir:hover { text-decoration: underline; }

  .vazio { padding: 48px 0; color: var(--tinta-2); max-width: 56ch; }

  @media (max-width: 640px) {
    h1 { font-size: 1.6rem; }
    li.edital { grid-template-columns: 64px 1fr; gap: 14px; }
    .prazo b { font-size: 1.9rem; }
    a.abrir { grid-column: 2; }
    .contagem { margin-left: 0; width: 100%; }
  }

  details.diag { margin-top: 48px; border-top: 2px solid var(--tinta); padding-top: 14px; }
  details.diag summary { cursor: pointer; font-weight: 700; font-size: 1.125rem; }
  .diag-topo { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 14px 0; }
  .diag-topo button { background: var(--papel); color: var(--aco); border: 1px solid var(--aco); }
  .diag h3 { font-size: 1rem; margin: 22px 0 8px; }
  .tab-diag { background: var(--papel); border: 1px solid var(--linha); border-radius: 6px;
              padding: 12px 14px; margin-bottom: 10px; overflow-x: auto; }
  .tab-diag p { margin: 0 0 6px; font-size: .875rem; color: var(--tinta-2); }
  .tab-diag table { border-collapse: collapse; font-size: .8125rem; }
  .tab-diag th, .tab-diag td { border: 1px solid var(--linha); padding: 4px 8px; text-align: left;
                               vertical-align: top; max-width: 280px; }
  .tab-diag th { background: var(--fundo); }
  .rede { font-size: .8125rem; word-break: break-all; }
  .rede li { padding: 6px 0; border-bottom: 1px solid var(--linha); }
  .rede .json { color: var(--musgo); font-weight: 700; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Editais SENAI-MG</h1>
      <div class="status" id="status">Carregando…</div>
    </div>
    <button id="btnColetar" type="button">Coletar agora</button>
  </header>

  <div class="filtros">
    <input type="search" id="busca" placeholder="Buscar por título, objeto ou unidade" aria-label="Buscar">
    <label><input type="checkbox" id="relevantes" checked> Só relevantes</label>
    <label><input type="checkbox" id="abertos" checked> Só abertos</label>
    <label><input type="checkbox" id="senai"> Só SENAI</label>
    <span class="contagem" id="contagem"></span>
  </div>

  <ol id="lista"></ol>

  <details class="diag" id="diag">
    <summary>Diagnóstico do portal</summary>
    <div class="diag-topo">
      <button id="btnDiag" type="button">Rodar diagnóstico</button>
      <span class="status" id="diagStatus"></span>
    </div>
    <div id="diagResultado"></div>
  </details>
</div>

<script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function hojeISO() { const d = new Date(); d.setHours(0,0,0,0); return d; }
function fmtData(iso) { if (!iso) return ""; const [y,m,d] = iso.slice(0,10).split("-"); return `${d}/${m}/${y}`; }
function fmtHora(iso) { return iso ? new Date(iso).toLocaleString("pt-BR", {dateStyle:"short", timeStyle:"short"}) : ""; }

function blocoPrazo(prazo) {
  if (!prazo) return `<div class="prazo sem"><b>?</b><span>sem prazo lido</span></div>`;
  const dias = Math.round((new Date(prazo + "T00:00:00") - hojeISO()) / 86400000);
  if (dias < 0) return `<div class="prazo encerrado"><b>fim</b><span>encerrado</span></div>`;
  const cls = dias <= 3 ? "urgente" : dias <= 10 ? "perto" : "folga";
  const rot = dias === 0 ? "encerra hoje" : dias === 1 ? "dia" : "dias";
  return `<div class="prazo ${cls}"><b>${dias}</b><span>${rot}</span></div>`;
}

function ehNovo(primeiroVisto) {
  return primeiroVisto && (Date.now() - new Date(primeiroVisto)) < 48 * 3600 * 1000;
}

async function carregar() {
  const p = new URLSearchParams({
    q: $("busca").value.trim(),
    relevantes: $("relevantes").checked,
    abertos: $("abertos").checked,
    senai: $("senai").checked,
  });
  const r = await fetch("/api/editais?" + p);
  const dados = await r.json();
  $("contagem").textContent = `${dados.length} ${dados.length === 1 ? "edital" : "editais"}`;
  if (!dados.length) {
    $("lista").innerHTML = `<li class="vazio">Nenhum edital com esses filtros. Desmarque algum filtro ou clique em "Coletar agora" para buscar novidades.</li>`;
    return;
  }
  $("lista").innerHTML = dados.map(e => `
    <li class="edital">
      ${blocoPrazo(e.prazo)}
      <div class="corpo">
        <h2>${esc(e.titulo)}</h2>
        ${e.objeto && e.objeto !== e.titulo ? `<p>${esc(e.objeto)}</p>` : ""}
        <div class="meta">
          ${ehNovo(e.primeiro_visto) ? `<span class="novo">Novo</span>` : ""}
          ${e.unidade ? `<span>${esc(e.unidade)}</span>` : ""}
          ${e.tipo ? `<span>${esc(e.tipo)}</span>` : ""}
          ${e.situacao ? `<span>${esc(e.situacao)}</span>` : ""}
          ${e.prazo ? `<span class="data">Prazo ${fmtData(e.prazo)}</span>` : ""}
        </div>
      </div>
      <a class="abrir" href="${esc(e.url)}" target="_blank" rel="noopener">Abrir edital</a>
    </li>`).join("");
}

async function atualizarStatus() {
  const s = await (await fetch("/api/status")).json();
  const el = $("status");
  $("btnColetar").disabled = s.rodando;
  $("btnColetar").textContent = s.rodando ? "Coletando…" : "Coletar agora";
  el.classList.remove("erro");
  if (s.rodando) { el.textContent = "Coleta em andamento."; return s; }
  if (!s.ultima) { el.textContent = "Nenhuma coleta feita ainda. Clique em Coletar agora."; return s; }
  const u = s.ultima;
  let txt = `Última coleta ${fmtHora(u.fim)}: ${u.encontrados} encontrados, ${u.novos} novos.`;
  if (s.proxima) txt += ` Próxima ${fmtHora(s.proxima)}.`;
  if (u.erros) { el.classList.add("erro"); txt += ` Erros: ${u.erros}`; }
  el.textContent = txt;
  return s;
}

$("btnColetar").addEventListener("click", async () => {
  $("btnColetar").disabled = true;
  await fetch("/api/coletar", { method: "POST" });
  const poll = setInterval(async () => {
    const s = await atualizarStatus();
    if (!s.rodando) { clearInterval(poll); carregar(); }
  }, 2500);
});

let timer;
$("busca").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(carregar, 300); });
["relevantes", "abertos", "senai"].forEach(id => $(id).addEventListener("change", carregar));

function tabelaDiag(t) {
  const cab = t.headers.length ? `<tr>${t.headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr>` : "";
  const lin = t.linhas.map(l => `<tr>${l.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("");
  return `<div class="tab-diag">
    <p>Tabela ${t.indice}${t.id ? ` (id ${esc(t.id)})` : ""}: ${t.total_linhas} linhas, amostra abaixo</p>
    <table>${cab}${lin || `<tr><td>sem linhas</td></tr>`}</table></div>`;
}

async function carregarDiag() {
  const d = await (await fetch("/api/diagnostico")).json();
  const st = $("diagStatus");
  $("btnDiag").disabled = d.rodando;
  $("btnDiag").textContent = d.rodando ? "Rodando…" : "Rodar diagnóstico";
  st.classList.toggle("erro", !!d.erro);
  if (d.rodando) { st.textContent = "Abrindo o portal, pode levar até 1 minuto."; return d; }
  if (d.erro) st.textContent = "Falhou: " + d.erro;
  const r = d.resultado;
  if (!r) { if (!d.erro) st.textContent = "Nenhum diagnóstico feito ainda."; $("diagResultado").innerHTML = ""; return d; }
  if (!d.erro) st.textContent = `Último diagnóstico ${fmtHora(r.quando)}: ${r.tabelas.length} tabelas, ${r.rede.length} chamadas AJAX.`;
  const comDados = r.tabelas.filter(t => t.total_linhas > 0 || t.headers.length);
  $("diagResultado").innerHTML = `
    <p><a class="abrir" href="/diagnostico-arquivos/tela.png?t=${Date.now()}" target="_blank" rel="noopener">Ver captura da tela</a></p>
    <h3>Tabelas com conteúdo (${comDados.length})</h3>
    ${comDados.map(tabelaDiag).join("") || "<p>Nenhuma tabela com conteúdo.</p>"}
    <h3>Chamadas AJAX (${r.rede.length})</h3>
    <ol class="rede">${r.rede.map(c => `<li>
      ${c.tipo.includes("json") ? `<span class="json">JSON</span> ` : ""}${esc(c.metodo)} ${c.status} ${esc(c.url)}
    </li>`).join("") || "<li>Nenhuma.</li>"}</ol>`;
  return d;
}

$("btnDiag").addEventListener("click", async () => {
  $("btnDiag").disabled = true;
  await fetch("/api/diagnostico", { method: "POST" });
  const poll = setInterval(async () => {
    const d = await carregarDiag();
    if (!d.rodando) clearInterval(poll);
  }, 3000);
});
$("diag").addEventListener("toggle", e => { if (e.target.open) carregarDiag(); });

atualizarStatus();
carregar();
</script>
</body>
</html>
````
