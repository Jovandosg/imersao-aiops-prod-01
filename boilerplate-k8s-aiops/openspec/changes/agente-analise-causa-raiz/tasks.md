## 1. Banco e Alembic

- [x] 1.1 Remover `engine` e `async_session` de `database.py`, mantendo `Base` e `get_database_url` (D11)
- [x] 1.2 Criar `models/report.py` com `ReportStatus` (StrEnum dos seis status) e o modelo `Report` (colunas, `CheckConstraint` de status, índice GIN em `event_uids`, `updated_at` com `onupdate`) (D10)
- [x] 1.3 Inicializar o Alembic com o template async (`alembic init -t async alembic`) e ajustar o `env.py` para usar `get_database_url()` e `Base.metadata` (D10)
- [x] 1.4 Escrever a migration inicial da tabela `reports` (revisar à mão o GIN e o check) e validar `upgrade head` / `downgrade base` contra o PostgreSQL do `docker compose`

## 2. Configuração

- [x] 2.1 Implementar `agents/config.py`: `AGENT_MODEL_NAME` (padrão `claude-haiku-4-5`), `AGENT_MAX_ITERATIONS` (int, padrão 25), `MCP_SERVER_URL` (padrão `http://localhost:3001/mcp`), `ANALYSIS_RETRY_COOLDOWN_MINUTES` e `ANALYSIS_STALE_TIMEOUT_MINUTES` (float, padrão 30), com warning para valores inválidos, zero ou negativos; testes seguindo o padrão de `collector/config.py`
- [x] 2.2 Documentar as novas variáveis em `.env.example` e na tabela do `CLAUDE.md`, com o passo `uv run alembic upgrade head` (o `.env` local já foi criado com `ANTHROPIC_API_KEY` vazia)

## 3. Regra de deduplicação (pura)

- [x] 3.1 Implementar `agents/dedup.py::blocked_uids(reports, events, now, cooldown)` com as regras de ativo, CORRIGIDO (`timestamp` > `corrected_at`, fallback `updated_at`) e INCOMPLETO (`created_at` + cooldown) (D2, D3)
- [x] 3.2 Testes unitários cobrindo todos os cenários da spec `relatorios-analise`: uid novo, cada status ativo, CORRIGIDO antes e depois de `corrected_at`, `corrected_at` nulo, INCOMPLETO dentro e fora do cooldown, ativo prevalecendo sobre antigo, lote parcial e lote total

## 4. Repositório

- [x] 4.1 Implementar em `models/repository.py`: `mark_stale`, `find_overlapping` (operador `&&`), `create_in_analysis -> UUID`, `mark_incomplete` (condicional a EM_ANALISE), `recover_orphans` e `swap_batch` (`UPDATE` condicional do Problema 1 + `INSERT` dos demais, numa transação) (D4, D5, D9)
- [x] 4.2 Configurar o marker `db` (fixture que cria `aiops_k8s_test`, roda `alembic upgrade head` por sessão e `TRUNCATE` por teste) e o marker `e2e`; atualizar `addopts` para `-m 'not kind and not db and not e2e'` (D12)
- [x] 4.3 Testes `db`: migration e colunas, check de status inválido, `updated_at` avançando, overlap via GIN, `mark_stale` (antigo vira INCOMPLETO, recente não), `mark_incomplete` sem sobrescrever relatório fora de EM_ANALISE, `recover_orphans`, `swap_batch` preservando o id e abortando quando o lote já saiu de EM_ANALISE

## 5. Handler de análise

- [x] 5.1 Definir o protocolo `Analyzer` e implementar `agents/handler.py::AnalysisEventHandler(sessionmaker, analyzer, cooldown, stale_timeout, clock)` com a tx 1 (stale → candidatos → `blocked_uids` → insert EM_ANALISE), o analisador fora da transação e a linha de log por lote (D4, D6)
- [x] 5.2 Tratar falhas: erro de banco na tx 1 gera log e o lote é descartado; exceção do analisador gera log e `mark_incomplete`; lote liberado vazio não cria relatório nem chama o analisador
- [x] 5.3 Testes unitários do handler com repositório e analisador fakes: lote vazio após filtro, analisador recebendo só os liberados, EM_ANALISE gravado antes do analisador, falha do analisador, banco indisponível
- [x] 5.4 Teste `db` do handler com um analisador fake: o mesmo lote entregue duas vezes gera um único relatório; com o clock depois do cooldown, gera um segundo

## 6. Agente de análise

- [x] 6.1 Implementar `agents/prompt.py` com o prompt do PRD 002 (incluindo `**Conclusao:**`) e a serialização JSON dos eventos; teste de que os uids, reasons e messages do lote aparecem no prompt
- [x] 6.2 Implementar `agents/parser.py::parse_report(text, batch_uids)` (D8); testes cobrindo dois problemas, cabeçalho promovido e Resumo descartado, severidade e conclusão ausentes, uid estranho, uid duplicado, uid do lote não citado e resposta sem problemas
- [x] 6.3 Implementar `select_read_only(tools)` com warning para tool ausente; teste com uma lista contendo tools de escrita
- [x] 6.4 Implementar `agents/analyzer.py::RootCauseAnalyzer`: `MultiServerMCPClient` (`transport: "http"`) → tools filtradas → `create_agent` com `ChatAnthropic(max_retries=3)` e `ModelCallLimitMiddleware(run_limit, exit_behavior="end")` → `ainvoke` → texto da última `AIMessage` → `parse_report` → `swap_batch` ou `mark_incomplete` (D7)
- [x] 6.5 Implementar o retry de 3 tentativas com backoff na gravação do resultado e o log da resposta do agente quando as tentativas se esgotam (D9)
- [x] 6.6 Testes unitários do analyzer com MCP client e agente fakes: agente criado só com as tools de leitura, resposta com dois problemas leva a `swap_batch`, resposta vazia leva a `mark_incomplete`, falha de conexão do MCP propaga exceção

## 7. Integração com a aplicação

- [x] 7.1 No `lifespan` de `main.py`: expor `app.state.sessionmaker`, aguardar `recover_orphans` (erro → log, segue) **antes** de `collector.start()`, montar `RootCauseAnalyzer` + `AnalysisEventHandler` e injetá-los no `EventCollector`; warning se `ANTHROPIC_API_KEY` estiver vazia (D11)
- [x] 7.2 Remover `collector/handler.py` e `tests/test_handler.py` (requisito REMOVED da `coleta-eventos`)
- [x] 7.3 Teste da ordem do `lifespan`: a recuperação termina antes da primeira listagem (fonte fake), e o banco fora do ar no startup não impede o coletor de iniciar
- [x] 7.4 Rodar `uv run pytest`, `uv run pytest -m db` e `uv run pytest -m kind`, e garantir que tudo está verde

## 8. Teste ponta a ponta automatizado (kind + manifestos)

- [x] 8.1 Preparar o ambiente: `kind create cluster --name aiops` (se não existir), `docker compose up -d`, `uv run alembic upgrade head`, MCP Server via `ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes` com o contexto `kind-aiops` ativo e `ANTHROPIC_API_KEY` preenchida no `.env`
- [x] 8.2 Implementar `tests/test_e2e.py` (marker `e2e`), que é pulado com mensagem quando faltar contexto `kind-aiops`, PostgreSQL, MCP ou chave da Anthropic
- [x] 8.3 Fixture: recriar os namespaces `teste-a` e `teste-b`, aplicar `manifestos-k8s/nginx.yaml` em `teste-a` e `manifestos-k8s/kube-news.yaml` em `teste-b`, e aguardar (até 3 min) os Warnings `Failed`/`BackOff` dos dois namespaces
- [x] 8.4 Executar o fluxo real: `KubernetesEventSource().list()` → `select_events(watermark=None)` filtrado a `teste-a`/`teste-b` → `AnalysisEventHandler.handle()` com o `RootCauseAnalyzer` real
- [x] 8.5 Asserções: relatório COMPLETO de `teste-a` com uid do `nginx-*` e diagnóstico da imagem `ngin:latest`; relatório COMPLETO de `teste-b` com uid do `kubenews-*` e diagnóstico de senha, autenticação ou `DB_PASSWORD`; todo uid entregue presente em algum relatório; segunda chamada de `handle` sem relatório novo
- [x] 8.6 Salvar a resposta bruta do agente em `tests/fixtures/` e adicionar ao parser um teste unitário com ela
- [x] 8.7 Rodar `uv run pytest -m e2e` até ficar verde; se falhar por qualidade do diagnóstico, ajustar o prompt (e, em último caso, o modelo), registrando no `design.md` o que mudou e por quê

## 9. Validação ponta a ponta manual (app rodando)

- [x] 9.1 Com o ambiente de 8.1 e os manifestos aplicados, subir a app com `EVENT_COLLECTION_INTERVAL_MINUTES=0.5` e `ANALYSIS_RETRY_COOLDOWN_MINUTES=2`; confirmar no log a recuperação, a primeira coleta e o lote enviado ao agente
- [x] 9.2 Confirmar no banco (pgAdmin ou `psql`) que o relatório do lote saiu de EM_ANALISE e que existem relatórios por problema com `severity`, `namespace`, `title` e `event_uids`, incluindo o diagnóstico do nginx (`ngin:latest`) e do kube-news (senha do banco); registrar o tempo da análise
- [x] 9.3 Confirmar que, nos ciclos seguintes, os eventos já cobertos (COMPLETO) não disparam novas análises
- [x] 9.4 Cooldown de INCOMPLETO: forçar um relatório INCOMPLETO (por exemplo, com o MCP parado durante uma análise) e confirmar que o mesmo evento só é reanalisado depois do cooldown
- [x] 9.5 MCP indisponível: parar o MCP Server, provocar um evento novo (`kubectl scale deploy/nginx -n teste-a --replicas=2`) e confirmar o erro no log, o relatório INCOMPLETO e o loop vivo
- [x] 9.6 Restart durante a análise: matar a app (Ctrl+C) com um relatório EM_ANALISE, subir de novo e confirmar que ele virou INCOMPLETO antes da primeira coleta
- [x] 9.7 Banco fora do ar: `docker compose stop postgres` com a app rodando; confirmar o erro no log a cada lote e o loop vivo; religar e confirmar que o fluxo volta
- [x] 9.8 Registrar os resultados (passos, Markdown dos relatórios de referência, tempos e custo aproximado) em "Resultado da validação" no `design.md` e atualizar o roteiro do kind no README
