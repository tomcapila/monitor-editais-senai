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
  progresso.py               progresso e tempo limite da coleta e do diagnóstico
  diagnostico.py             inspeciona o portal real (usado pelo painel e pelo script)
  exportar.py                gera o painel estático (site/) para o GitHub Pages
  coletores/
    base.py                  modelo Edital + classe base
    fiemg_api.py             Portal de Compras FIEMG pelo serviço JSON do portal (padrão)
    fiemg_paradigma.py       Portal de Compras FIEMG lendo as tabelas do HTML (alternativa)
    pagina_links.py          páginas simples com links/PDFs (modelo p/ outros estados)
    demo.py                  dados fictícios para testar a interface
static/index.html            painel
scripts/diagnostico_fiemg.py diagnóstico pelo terminal (navegador visível)
.github/workflows/coleta.yml coleta agendada + publicação no GitHub Pages
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

## Progresso e tempo limite

O painel mostra uma barra com a etapa atual, o percentual e o tempo decorrido
enquanto a coleta ou o diagnóstico rodam. Os limites ficam no `config.yaml`:
`coleta.tempo_limite_segundos` (padrão 600) e
`diagnostico.tempo_limite_segundos` (padrão 180). Ao estourar, a tarefa para,
mantém o que já foi salvo e registra o erro no topo do painel.

## Coleta automática

Com o servidor rodando, a coleta acontece a cada `intervalo_horas`.
Se preferir sem servidor, agende `python -m app.coleta` no cron (Linux)
ou no Agendador de Tarefas (Windows).

## Publicar de graça (GitHub Actions + GitHub Pages)

O workflow `.github/workflows/coleta.yml` roda a coleta às 6h e às 18h
(Brasília) numa máquina do GitHub e publica o painel como página estática,
sem servidor. O banco fica no branch `dados`, reescrito a cada execução.

1. Crie um repositório **público** no GitHub (Pages grátis exige repositório
   público; os editais já são públicos, e `.env` e `editais.db` não sobem).
2. Envie o projeto: `git init`, `git add .`, `git commit -m "..."`,
   `git remote add origin <url>` e `git push -u origin main`.
3. No repositório, em **Settings > Pages**, escolha **Source: GitHub Actions**.
4. Em **Actions > Coleta de editais**, clique em **Run workflow**. Quando
   terminar, o endereço do painel aparece no resumo da execução
   (`https://<usuario>.github.io/<repositorio>/`).
5. Alertas (opcional): em **Settings > Secrets and variables > Actions**, crie
   os mesmos nomes do `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` ou os
   `SMTP_*` e `EMAIL_PARA`) e ligue `telegram` ou `email` no `config.yaml`.

Na versão publicada, "Coletar agora" abre a página do workflow (clique em
**Run workflow** e recarregue o painel depois) e o diagnóstico fica escondido,
porque precisa do servidor local. Para gerar a página estática à mão:
`python -m app.exportar` (cria a pasta `site/`).

A primeira execução no GitHub não dispara alertas, como a primeira coleta local.
O GitHub pode pausar workflows agendados de repositórios sem atividade por
60 dias; ele avisa por e-mail e basta reativar em Actions.

## Limitações conhecidas

- O coletor `fiemg_api` foi validado contra o portal real em 27/09/2026. Ele
  abre o mural no Playwright (o site passa pelo Cloudflare) e chama o serviço
  `WebService/Servicos.asmx/PesquisarProcessos` de dentro da página. Se o
  portal mudar, rode o diagnóstico e, se preciso, volte para `fiemg_paradigma`.
- O mural não informa prazo de inscrição (o portal manda a data final vazia).
  O prazo costuma estar no PDF anexado ao processo, que ainda não é lido.
- As listas de chamamentos e RFIs da tela "Edital simplificado" estavam vazias
  no próprio portal em 27/09/2026; o coletor as consulta mesmo assim.
- `max_registros: 200` cobre cerca de duas semanas de processos. Com coleta a
  cada 12 horas isso sobra; aumente se o monitor ficar dias desligado.
- A detecção de prazo em PDF é heurística. Confira sempre no edital.
- Mudanças no layout do portal quebram o coletor. Fique de olho nos erros
  mostrados no topo do painel.
- Mantenha frequência baixa de acesso e respeite os termos de uso do portal.

## Adicionar outro estado

Crie um módulo em `app/coletores/` herdando de `Coletor`, devolva uma lista de
`Edital` em `coletar()`, registre o tipo em `app/coletores/__init__.py` e
adicione a fonte no `config.yaml`. Para sites simples, `pagina_links` já pode
servir sem código novo.
