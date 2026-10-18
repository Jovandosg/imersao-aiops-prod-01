# CLAUDE.md

## Sobre o projeto

<!-- TODO: Descreva o proposito do seu agente aqui -->
Boilerplate para agente inteligente com FastAPI + LangChain + MCP Server.

## Comandos

```bash
# Instalar dependencias
uv sync

# Executar aplicacao
uv run uvicorn my_agent_app.main:app --host 0.0.0.0 --port 8000

# Subir o banco de dados (Docker so provisiona PostgreSQL + pgAdmin)
docker compose up -d

# Subir o MCP Server Kubernetes localmente via npx (transport HTTP/streamable, porta 3001)
# Requer Node.js/npx instalado e kubeconfig em ~/.kube/config
ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes

# Aplicar migrations do banco de dados (obrigatorio antes de subir a app)
uv run alembic upgrade head
```

A aplicacao roda localmente via `uv`; o Docker e usado apenas para o banco de dados.
O MCP Server roda localmente via `npx` expondo transport HTTP, e o LangChain conecta por HTTP (`MCP_SERVER_URL`).

```bash
# Testes unitarios (sem cluster)
uv run pytest

# Testes de integracao contra o kind local (contexto kind-aiops; roteiro no README)
uv run pytest -m kind

# Testes de banco (PostgreSQL do docker compose; cria e migra o banco aiops_k8s_test)
uv run pytest -m db

# Fluxo completo: kind + PostgreSQL + MCP Server + ANTHROPIC_API_KEY (faz chamadas reais e pagas)
uv run pytest -m e2e
```

Nao ha linter configurado ainda.

## Arquitetura

O codigo da aplicacao fica em `src/my_agent_app/` e e empacotado via hatchling (`pyproject.toml`).

- **Database** (`database.py`) — Engine async SQLAlchemy + asyncpg, configurado via `DATABASE_URL`
- **API** (`api/router.py`) — Health check
- **Interface Web** (`web/`) — `router.py` (home, `GET /reports`, `GET /reports/{id}`, `POST /reports/{id}/fix` com transicao atomica e 303; 503 em banco indisponivel) e `rendering.py` (`render_markdown`: Markdown → HTML no servidor, HTML embutido escapado). Templates Jinja2 em `src/my_agent_app/templates/` (`reports.html`, `report_detail.html`)
- **Collector** (`collector/`) — Loop de coleta de eventos Warning (`events.k8s.io/v1`) iniciado no `lifespan`: `config.py` (intervalo), `k8s.py` (autenticacao + listagem crua), `transform.py` (recencia, janela, contrato), `loop.py` (`EventCollector`, marca d'agua, despacho fire-and-forget)
- **Agents** (`agents/`) — Pipeline de analise de causa raiz: `config.py` (env vars do agente), `dedup.py` (`blocked_uids`, funcao pura), `handler.py` (`AnalysisEventHandler`: dedup → relatorio EM_ANALISE → analisador), `prompt.py` (prompt do PRD 002), `parser.py` (`parse_report`, um `Problem` por secao), `analyzer.py` (`RootCauseAnalyzer`: MCP → tools somente leitura → `create_agent` → parse → troca do lote). Correcao: `correction_prompt.py` (prompt do PRD 004), `verdict.py` (`parse_verdict`, funcao pura, qualquer `FALHA:` vence), `corrector.py` (`Corrector`: MCP com todas as tools → agente sob `asyncio.timeout` → veredito → `finish_correction` condicional a CORRIGINDO) e `correction_executor.py` (`CorrectionExecutor`: `create_task` fire-and-forget, cancelado no shutdown)
- **Models** (`models/`) — `report.py` (`Report`, `ReportStatus`, `correction_started_at`) e `repository.py` (consultas e transicoes condicionais; o chamador controla a transacao). Migrations em `alembic/`
- **Lifespan** (`main.py`) — Um unico `async_sessionmaker` em `app.state.sessionmaker` e o `CorrectionExecutor` em `app.state.correction_executor`; recuperacao de orfaos (EM_ANALISE → INCOMPLETO, CORRIGINDO → FALHA_CORRECAO, mesma transacao) aguardada antes de `collector.start()`; shutdown na ordem coletor → executor → engine
- **Scripts** (`scripts/seed_reports.py`) — Relatorios de exemplo nos seis status: `uv run python scripts/seed_reports.py`

## Variaveis de ambiente

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `ANTHROPIC_API_KEY` | Chave de API da Anthropic | (obrigatorio) |
| `DATABASE_URL` | Connection string PostgreSQL async | `postgresql+asyncpg://aiops:aiops123@localhost:5432/aiops_k8s` |
| `MCP_SERVER_URL` | Endpoint HTTP do MCP Server Kubernetes (via npx) | `http://localhost:3001/mcp` |
| `EVENT_COLLECTION_INTERVAL_MINUTES` | Intervalo da coleta de eventos Warning, em minutos (aceita fracao; invalido cai no padrao) | `3` |
| `AGENT_MODEL_NAME` | Modelo Claude do agente de analise | `claude-haiku-4-5` |
| `AGENT_MAX_ITERATIONS` | Limite de chamadas ao modelo por analise (inteiro positivo; invalido cai no padrao) | `25` |
| `ANALYSIS_RETRY_COOLDOWN_MINUTES` | Minutos ate um relatorio INCOMPLETO poder ser reanalisado, contados do `created_at` (aceita fracao) | `30` |
| `ANALYSIS_STALE_TIMEOUT_MINUTES` | Minutos ate um relatorio EM_ANALISE ser marcado INCOMPLETO por estagnacao (aceita fracao) | `30` |
| `CORRECTION_MODEL_NAME` | Modelo Claude do agente de correcao (vazio usa `AGENT_MODEL_NAME`) | `AGENT_MODEL_NAME` |
| `CORRECTION_MAX_ITERATIONS` | Limite de chamadas ao modelo por correcao (inteiro positivo; invalido cai no padrao) | `25` |
| `CORRECTION_TIMEOUT_MINUTES` | Tempo limite de uma correcao, em minutos (aceita fracao); a varredura de estagnacao usa 2x esse valor | `10` |

## Infraestrutura (docker-compose)

O Docker provisiona **apenas o banco de dados** (PostgreSQL + pgAdmin). A aplicacao e o MCP Server rodam localmente.

| Servico | Porta | Credenciais |
|---------|-------|-------------|
| PostgreSQL 17 | 5432 | aiops / aiops123 / aiops_k8s |
| pgAdmin | 5050 | admin@admin.com / admin123 |
