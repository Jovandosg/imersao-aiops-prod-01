## Why

O coletor (PRD 001) entrega Warnings a cada ciclo, mas ninguém os analisa. Hoje o diagnóstico de causa raiz é manual (30 min a 2 h) e não deixa registro. Esta change implementa o PRD 002 inteiro, os dois milestones: os eventos coletados são deduplicados, investigados por um agente LangChain + Claude que usa o MCP Server Kubernetes em modo somente leitura, e viram relatórios Markdown persistidos, um por problema. A entrega só está pronta quando o fluxo completo diagnosticar corretamente os cenários de referência de `manifestos-k8s/` num cluster kind.

## What Changes

- **Persistência**: Alembic (async) e migration inicial da tabela `reports` (`id` UUID, `markdown`, `status`, `event_uids` `TEXT[]` com GIN, `severity`, `namespace`, `title`, `created_at`, `updated_at`, `corrected_at`, `correction_result`). Modelo `Report` e enum de status em `models/`.
- **Deduplicação por uid com predicado temporal**:
  - ignora uids vinculados a relatórios ativos;
  - libera um CORRIGIDO só se o `timestamp` do evento for posterior a `corrected_at`;
  - libera um INCOMPLETO só depois de `ANALYSIS_RETRY_COOLDOWN_MINUTES` (padrão 30), contado do `created_at`.
- **Ciclo de vida**: um relatório EM_ANALISE por lote, gravado antes da análise; timeout de estagnação (`ANALYSIS_STALE_TIMEOUT_MINUTES`, padrão 30); recuperação de órfãos no startup, aguardada **antes** de `collector.start()`.
- **Agente de análise**: `create_agent` com `ChatAnthropic` (`AGENT_MODEL_NAME`, padrão `claude-haiku-4-5`, `max_retries=3`), `ModelCallLimitMiddleware(run_limit=AGENT_MAX_ITERATIONS, exit_behavior="end")` e tools do MCP Server Kubernetes via `langchain-mcp-adapters` (`transport: "http"`, `MCP_SERVER_URL`), filtradas para `kubectl_get`, `kubectl_describe` e `kubectl_logs`. O prompt é o do PRD 002, incluindo o campo `**Conclusao:**`.
- **Parse e troca do relatório**:
  - a resposta é dividida em uma seção por problema, de onde saem `severity`, `namespace`, `title`, o status (pelo campo `**Conclusao:**`) e os `event_uids`, validados contra o lote;
  - o relatório do lote vira o Problema 1 por `UPDATE` condicional a EM_ANALISE, e os demais problemas são inseridos na mesma transação;
  - resposta vazia ou sem seções, MCP indisponível ou erro da API → INCOMPLETO.
- **Integração**: `AnalysisEventHandler` (deduplicação → EM_ANALISE → agente) substitui o handler de impressão no `lifespan`. Um único `async_sessionmaker` em `app.state.sessionmaker`; o engine no nível de módulo sai de `database.py`. **BREAKING** (interno): `database.engine` e `database.async_session` deixam de existir. O handler placeholder `collector/handler.py` é removido.
- **Validação ponta a ponta**: novo marker pytest `e2e` (kind + PostgreSQL + MCP + chave Anthropic). Com `nginx.yaml` em `teste-a` e `kube-news.yaml` em `teste-b`, o teste exige relatórios COMPLETO que apontem a imagem inexistente `ngin:latest` e a senha divergente do banco do kube-news. A mesma validação também é feita com a aplicação rodando, num roteiro manual.
- **Configuração**: novas env vars `AGENT_MODEL_NAME`, `AGENT_MAX_ITERATIONS`, `ANALYSIS_RETRY_COOLDOWN_MINUTES` e `ANALYSIS_STALE_TIMEOUT_MINUTES`; `.env` local para a `ANTHROPIC_API_KEY`.

## Capabilities

### New Capabilities
- `relatorios-analise`: modelo persistido de relatórios, ciclo de status, deduplicação por uid com predicado temporal, EM_ANALISE gravado antes da análise, timeout de estagnação e recuperação de órfãos.
- `agente-analise`: agente de causa raiz (modelo, limite de iterações, tools somente leitura via MCP), prompt, parse da resposta em relatórios por problema, troca condicional do relatório do lote, tratamento de falhas e diagnóstico dos cenários de referência do kind.

### Modified Capabilities
- `coleta-eventos`: o requisito "Exibição dos eventos coletados no stdout" é removido. O handler placeholder dá lugar ao pipeline de análise, e a visibilidade passa a vir dos relatórios no banco e do log do handler.

## Impact

- **Código**: `models/` (modelo, repositório), `agents/` (config, deduplicação, handler, agente, prompt, parser), `database.py`, `main.py`. Removidos: `collector/handler.py` e `tests/test_handler.py`.
- **Banco**: tabela `reports`; `alembic/` e `alembic.ini`; `uv run alembic upgrade head` antes de subir a app.
- **Serviços externos**: API da Anthropic (custo por análise) e MCP Server Kubernetes via `npx` apontando para o contexto do cluster.
- **Testes**: marker `db` (PostgreSQL do `docker compose`, banco `aiops_k8s_test`) e marker `e2e` (fluxo completo). Os dois ficam fora da execução padrão.
- **Downstream**: o PRD 003 lê a tabela `reports` e o PRD 004 preenche `corrected_at` e `correction_result`.
