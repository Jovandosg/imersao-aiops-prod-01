## Context

A change `agente-analise-causa-raiz` (PRD 002) está implementada: a tabela `reports` existe com os seis status, `corrected_at` e `correction_result`. Há um único `async_sessionmaker` em `app.state.sessionmaker`, e o `AnalysisEventHandler` roda a cada lote do coletor. A camada web tem só a home (`web/router.py`) e os templates `base.html`, `home.html` e `error.html`, ainda com "Tasks" do boilerplate. O `base.html` já define as classes de badge dos seis status. `markdown>=3.10.2` e `jinja2` já são dependências.

Esta change entrega os PRDs 003 e 004 como estão no repositório em 2026-10-18, incluindo as decisões tomadas na revisão:
- conversão do Markdown no servidor com HTML embutido escapado;
- despacho via `create_task`;
- invariante de saída de CORRIGINDO;
- veredito conservador;
- `CORRECTION_MODEL_NAME`.

Padrões do código atual que esta change reaproveita:
- **Despacho fire-and-forget com cancelamento**: `EventCollector._handler_tasks` + `stop()`.
- **Transições condicionais com retorno booleano**: `repository.swap_batch`, `mark_incomplete`.
- **Persistência com retry**: `RootCauseAnalyzer._persist` com `RETRYABLE_DB_ERRORS`.
- **Construção por execução**: cliente MCP e agente criados a cada análise, com fábricas injetáveis para teste.
- **Env vars com fallback e warning**: `agents/config.py`.

## Goals / Non-Goals

**Goals:**
- Operador lê relatórios no navegador e aciona a correção pelo detalhe.
- Nunca dois agentes de correção no mesmo relatório, nem por clique duplo, nem por estagnação ou retry.
- Toda correção termina em CORRIGIDO ou FALHA_CORRECAO com `correction_result` legível, inclusive após timeout, erro ou restart.
- Testável sem cluster e sem API paga, com uma validação e2e no kind.

**Non-Goals:**
- Autenticação, CSRF, prompt injection, whitelist de tools, dry-run, rollback (aceitos nos PRDs).
- Atualização automática da página (polling/JS): o operador recarrega.
- Paginação e filtros.
- Execução com múltiplos workers do uvicorn: a recuperação de órfãos assume um único processo (mesma premissa do PRD 002).

## Decisions

### D1. Layout dos módulos
```
web/
├── router.py        # /, /reports, /reports/{id}, POST /reports/{id}/fix
└── rendering.py     # render_markdown(md) -> Markup  (lib markdown + EscapeHtml)
templates/
├── base.html        # link "Relatórios"
├── error.html       # "Voltar para relatórios"
├── reports.html     # listagem
└── report_detail.html   # detalhe, estados vazios, botão, mensagens, Resultado da Correção
agents/
├── config.py              # + CORRECTION_MODEL_NAME, CORRECTION_MAX_ITERATIONS, CORRECTION_TIMEOUT_MINUTES
├── correction_prompt.py   # prompt do PRD 004
├── verdict.py             # parse_verdict(text) -> status  — função pura
├── corrector.py           # Corrector: MCP (todas as tools) → agente → veredito → gravação final
└── correction_executor.py # CorrectionExecutor: dispatch(report_id), stop()
models/
├── report.py        # + correction_started_at
└── repository.py    # + list_reports, get_report, start_correction, finish_correction,
                     #   recover_correction_orphans, mark_correction_stale
scripts/
└── seed_reports.py
```
As rotas de relatório ficam em `web/router.py`, como o PRD pede (é HTML, não API). A correção fica em `agents/`, lado a lado com a análise, mas em módulos separados (decisão-chave 1 do PRD 004). `analyzer.final_text` é reaproveitado pelo `Corrector`.

*Alternativa:* subpacote `agents/correction/`. O projeto hoje é plano e cada módulo é pequeno. O prefixo `correction_` basta.

### D2. Renderização do Markdown
`render_markdown` usa `markdown.markdown(md, extensions=["fenced_code", "tables", EscapeHtml()])` e devolve `markupsafe.Markup` para o template não escapar de novo. `EscapeHtml` remove o preprocessor `html_block` e o inline pattern `html`. Sem eles, o serializer da lib escapa o HTML cru, como documentado pelo Python-Markdown. A mesma função renderiza `markdown` e `correction_result`.

*Alternativas:*
- **bleach/nh3 depois da conversão**: removeria `<none>` em vez de exibi-lo, e adicionaria uma dependência.
- **Conversão no navegador**: descartada pelo usuário. O PRD 003 fixa a conversão no servidor.

### D3. Leitura de status e 503
`list_reports(session)` e `get_report(session, id)` são consultas simples. Cada rota envolve a leitura em `try/except (SQLAlchemyError, OSError)` → `error.html` com 503. Um helper no router evita repetir o bloco. O 404 usa o mesmo `error.html` com `status_code=404`.

### D4. Transição para CORRIGINDO e escolha do conflito
```
POST /reports/{id}/fix
 └─ tx:  UPDATE reports SET status='CORRIGINDO', correction_started_at=now(),
                            correction_result=NULL, updated_at=now()
         WHERE id=:id AND status IN ('COMPLETO','FALHA_CORRECAO') RETURNING id
         ├─ linha  → commit → executor.dispatch(id) → 303 /reports/{id}
         └─ vazio  → SELECT status WHERE id=:id
                      ├─ None        → 404
                      ├─ CORRIGINDO  → 303 ?erro=em_andamento
                      └─ outro       → 303 ?erro=status_invalido
```
O `dispatch` só ocorre **depois** do commit. Assim a task nunca lê um relatório ainda não comitado. O SELECT de conflito não precisa de lock: ele só escolhe a mensagem, e a corrida já foi decidida pelo UPDATE. Banco indisponível no POST → 503 com `error.html`.

### D5. Executor de correção
`CorrectionExecutor` espelha o despacho do `EventCollector`: `dispatch(report_id)` faz `asyncio.create_task(self._run(report_id))`, guarda a task num `set` e a remove com `add_done_callback`. `stop()` cancela todas e espera com `gather(return_exceptions=True)`. Fica criado no `lifespan` em `app.state.correction_executor`. A rota o obtém via `request.app.state`.

Ordem no shutdown: `collector.stop()` → `correction_executor.stop()` → `engine.dispose()`.

O cancelamento por shutdown **não** grava FALHA_CORRECAO, porque o engine está sendo descartado e o processo vai morrer. O relatório fica em CORRIGINDO e a recuperação do próximo startup o resolve. Por isso `_run` captura `Exception`, mas não `CancelledError` (que é `BaseException`).

*Alternativa:* `BackgroundTasks` do FastAPI. Descartado no PRD 004: fica preso ao ciclo do request e não é cancelável no shutdown.

### D6. Ciclo do Corrector
```
_run(report_id)
 ├─ tx curta: SELECT markdown           (sessão própria, nunca a do request)
 ├─ async with asyncio.timeout(timeout_s):
 │     client = client_factory({"k8s": {"transport": "http", "url": MCP_SERVER_URL}}, handle_tool_errors=True)
 │     tools  = await client.get_tools()            # todas, sem filtro
 │     agent  = agent_factory(tools, config)        # ChatAnthropic(max_retries=3) + ModelCallLimitMiddleware
 │     result = await agent.ainvoke(prompt(markdown))
 │     text   = final_text(result["messages"]); status = parse_verdict(text)
 ├─ except TimeoutError  → status=FALHA_CORRECAO, result=MSG_TIMEOUT(N)
 ├─ except Exception     → status=FALHA_CORRECAO, result=MSG_ERRO(exc)   (log.exception)
 └─ finish_correction(id, status, result)  com retry (PERSIST_ATTEMPTS, backoff 1s/2s)
```
O timeout envolve **tudo o que toca o agente ou o MCP**, inclusive `get_tools()`. Dentro do `async with asyncio.timeout`, o estouro cancela a coroutine em andamento, então o agente para de fato antes da gravação. Isso garante o invariante "sair de CORRIGINDO só com o agente parado".

**Erro de execução de tool não é falha da correção.** O MCP Server Kubernetes sinaliza toda falha do kubectl (patch inválido, recurso inexistente, `rollout status` que estoura o timeout) com erro JSON-RPC, que o adaptador levanta como `McpError`. O `handle_tool_errors=True` do `langchain-mcp-adapters` 0.3.0 só cobre resultados `isError=True`, então esse erro abortaria o agente inteiro, contrariando a regra do prompt de ler o erro e tentar outra abordagem. Por isso o cliente recebe `tool_interceptors=[tool_errors_as_results]`, que converte o `McpError` de uma chamada de tool em `CallToolResult(isError=True)`; o agente o recebe como `ToolMessage` de erro. Falhas de conexão e de transporte (`get_tools`, abertura de sessão) continuam propagando e levam a FALHA_CORRECAO. Descoberto no primeiro e2e real: a correção do nginx abortou em 34 s com `MCP error -32603: Failed to execute rollout command: spawnSync kubectl ETIMEDOUT`.

`finish_correction` é `UPDATE ... WHERE id=:id AND status='CORRIGINDO'` com `corrected_at=now()` só quando o status é CORRIGIDO. Retorna `False` se o relatório já saiu de CORRIGINDO; nesse caso, warning e descarte.

### D7. Parser do veredito
`parse_verdict(text) -> str` percorre as linhas e procura a regex `^\s*(?:[-*#>]+\s*)*(?:\*\*|__)?(CORRIGIDO|FALHA)(?:\*\*|__)?\s*:` (com tolerância a `**CORRIGIDO:**`). Junta os tokens encontrados:
- qualquer `FALHA` → `FALHA_CORRECAO`;
- só `CORRIGIDO` → `CORRIGIDO`;
- nenhum → `FALHA_CORRECAO` + warning.

É função pura, coberta por testes unitários com os cenários da spec.

### D8. Órfãos e estagnação de CORRIGINDO
- **Startup**: `main.recover_orphans` passa a chamar, na mesma transação, `repository.recover_orphans` (EM_ANALISE) e `repository.recover_correction_orphans` (CORRIGINDO → FALHA_CORRECAO + `MSG_INTERROMPIDA`). Mantém o comportamento atual: falha de banco só gera log.
- **Estagnação**: `AnalysisEventHandler._register` chama `repository.mark_correction_stale(session, now, 2 × timeout)` logo após `mark_stale`, na Tx 1. O handler recebe o timeout de correção no construtor.

A varredura usa `correction_started_at`, nunca `created_at` (o relatório pode ter dias) nem `updated_at`, que é implícito e frágil. O fator 2× é fixo no código e não é configurável, para que não exista configuração em que a varredura alcance um agente vivo.

*Trade-off aceito:* a Tx 1 só roda quando o coletor tem um lote. Num cluster sem Warnings, um relatório preso por falha da gravação final só é resolvido no próximo lote ou no próximo restart. Como o timeout já parou o agente, o custo é apenas o botão indisponível por mais tempo. *Alternativa:* um loop próprio de varredura. Seria mais uma task de vida longa no `lifespan` para um caso raro.

### D9. Migration
Nova revisão Alembic `add_correction_started_at`: `op.add_column("reports", sa.Column("correction_started_at", sa.DateTime(timezone=True), nullable=True))`, com `downgrade` que remove a coluna. Não altera dados existentes.

### D10. Configuração
Em `agents/config.py`, seguindo `_positive_minutes` e `get_agent_max_iterations`:
- `get_correction_model_name()`: `CORRECTION_MODEL_NAME` ou `get_agent_model_name()`;
- `get_correction_max_iterations()`: padrão 25;
- `get_correction_timeout_minutes()`: padrão 10, aceita fração.

Um `CorrectorConfig.from_env()` frozen dataclass espelha o `AgentConfig`.

### D11. Prompt de análise (D15 do PRD 002)
Em `agents/prompt.py`, o exemplo de `### Comando Sugerido` passa de `--type=merge` para `--type=strategic`. É uma mudança de uma linha. O teste de prompt existente cobre que o template continua íntegro.

### D12. Estratégia de testes
| Camada | O que cobre | Como |
|---|---|---|
| Unitário | `parse_verdict`, config, prompt de correção, `render_markdown` (`<none>` → `&lt;none&gt;`, tabela, código), executor (dispatch não bloqueia, `stop()` cancela), Corrector com fakes (veredito, timeout com agente que dorme, exceção, MCP fora, retry de gravação, resultado descartado) | `client_factory`/`agent_factory`/`repository`/`sleep` injetados, como em `test_analyzer.py` |
| Rotas | listagem (ordem, "—", "Análise em lote", vazio), badges, detalhe, estados vazios, 404, 422, 503 (`OperationalError` e `ConnectionRefusedError`), botão por status, mensagens `?erro=`, seção de resultado | `TestClient` com repositório substituído por fake; 503 por fake que levanta |
| `db` | `start_correction` (transição, `correction_started_at`, limpeza de `correction_result`), concorrência (`asyncio.gather` de dois `start_correction` em sessões distintas → um `True`), `finish_correction` (CORRIGIDO preenche `corrected_at`, FALHA não altera, não sobrescreve), órfãos, estagnação antes/depois de 2×, migration | PostgreSQL do `docker compose`, fixtures existentes |
| `e2e` | os dois cenários de `manifestos-k8s/`, da análise real até o cluster saudável, passando pela interface web (D13) | kind + PostgreSQL + MCP + API Anthropic, marker existente |

Testes de rota usam o lifespan desligado e um `app.state` montado à mão, para não subir o coletor.

### D13. Teste de ponta a ponta da correção
Arquivo novo `tests/test_e2e_correcao.py` com o marker `e2e`. As pré-condições e o preparo do cluster são os do `tests/test_e2e.py` atual: contexto `kind-aiops`, `ANTHROPIC_API_KEY`, MCP respondendo, namespaces `teste-a`/`teste-b` recriados, manifestos aplicados e espera pelos Warnings `Failed`/`BackOff`. Esses helpers saem do `test_e2e.py` para `tests/e2e_support.py`, compartilhado pelos dois módulos.

```
fixture scenarios            recria teste-a/teste-b, kubectl apply nginx.yaml / kube-news.yaml, espera Warnings
   │
análise real                 AnalysisEventHandler + RootCauseAnalyzer (como no test_e2e.py)
   │                         → relatórios COMPLETO do nginx e do kubenews (mesmos critérios de seleção)
   ▼
app em processo              FastAPI com web_router; app.state.sessionmaker + CorrectionExecutor(Corrector real)
   │                         httpx.AsyncClient(ASGITransport) — sem lifespan, sem coletor
   ├─ GET /reports           os dois relatórios listados com badge-complete
   ├─ GET /reports/{id}      detalhe com o botão "Executar correção"
   ├─ POST /reports/{id}/fix 303 → /reports/{id}; status CORRIGINDO
   ├─ espera                 poll do banco até sair de CORRIGINDO (limite: CORRECTION_TIMEOUT_MINUTES + margem)
   └─ asserções              banco, interface e cluster (abaixo)
```

- **Correções em sequência**: nginx primeiro, depois kube-news. Uma falha fica atribuível a um cenário, e um agente não observa o outro mexendo no cluster.
- **Asserções no banco**: status CORRIGIDO, `corrected_at` preenchido, `correction_result` com a seção "Ações Executadas". Se o status for FALHA_CORRECAO, a mensagem do `assert` traz o `correction_result`.
- **Asserções no cluster**, via `kubernetes` client, com espera de até 180 s para rollout. A espera é do teste, não do agente: o agente pode declarar CORRIGIDO com os pods ainda subindo.
  - `nginx`: imagem ≠ `ngin:latest`, `containerPort` 80 mantido, `availableReplicas == replicas`, pods Running/Ready.
  - `kubenews`: `DB_PASSWORD` igual ao `POSTGRES_PASSWORD` do `postgre` (aceita corrigir qualquer um dos dois lados); imagem, `DB_HOST`, `DB_DATABASE`, `DB_USERNAME` e `replicas: 10` preservados; 10 réplicas Ready. Essa é a asserção que pega o merge patch destrutivo proibido pelo prompt.
- **Asserções na interface depois da correção**: `badge-executed` na listagem, seção "Resultado da Correção" no detalhe, botão ausente, novo `POST /fix` → `?erro=status_invalido`.
- **Captura das respostas**: as respostas brutas do agente de correção são gravadas em `tests/fixtures/e2e_correction_responses.json` quando o arquivo não existe, no mesmo padrão do `e2e_agent_response.json`. Elas viram casos reais para os testes unitários de `parse_verdict`.
- **Custo**: uma análise e duas correções reais por execução. O cluster fica com os cenários corrigidos ao fim; a próxima execução recria os namespaces.

## Risks / Trade-offs

- [Agente com escrita irrestrita age sobre um diagnóstico errado] → Aceito na v1 (PRD 004). O operador revisa o relatório antes de clicar; o prompt proíbe deletar namespaces/PVCs/`kube-system` e escalar para 0.
- [Timeout cancela a correção no meio, deixando o cluster parcialmente alterado] → A mensagem fixa avisa que ações parciais podem ter sido aplicadas. Na nova tentativa, o prompt manda verificar o estado atual antes de agir.
- [Falso FALHA_CORRECAO com pods ainda estabilizando] → Limitação conhecida do PRD 004 (US02). A nova tentativa está disponível. No e2e, isso pode tornar o teste instável, principalmente no kube-news, com 10 réplicas: se acontecer, o `correction_result` mostrado no `assert` diz se foi estabilização ou erro real.
- [Haiku como padrão pode ser fraco para corrigir] → `CORRECTION_MODEL_NAME` permite um modelo mais forte só na correção.
- [Mesmo MCP Server serve análise e correção] → A análise continua filtrando para somente leitura no cliente (`select_read_only`). O servidor em si é irrestrito.
- [Varredura acoplada ao handler de análise] → Aceito pela simplicidade (D8). Se crescer, vira um passo próprio do ciclo.
- [Múltiplos workers do uvicorn] → Um worker marcaria como órfãs as correções vivas de outro. Fora do escopo: o projeto roda com um processo.

## Migration Plan

1. `uv run alembic upgrade head` aplica a coluna `correction_started_at` (aditiva, nula).
2. Novas env vars são opcionais, todas com padrão. Documentar em `.env.example` e `CLAUDE.md`.
3. Rollback: reverter o código e `uv run alembic downgrade -1`. Relatórios em CORRIGIDO/FALHA_CORRECAO continuam válidos no schema anterior.
4. Arquivar `agente-analise-causa-raiz` antes desta change, para que as specs base existam em `openspec/specs/`.

## Open Questions

- Nomes dos registros a remover no Python-Markdown 3.10 (`html_block`, `html`) e a API `deregister`: confirmar na implementação contra a doc da versão travada.
- Timeouts padrão do transport `streamable_http` no `langchain-mcp-adapters`: com o timeout no task não bloqueiam, mas um timeout de leitura menor no cliente daria erros mais claros que o cancelamento genérico.

## Validação

### Roteiro manual no navegador (10.7) — 2026-10-18

App em `:8765` contra o banco `aiops_k8s_test` com `scripts/seed_reports.py`, em modo isolado: `ANTHROPIC_API_KEY` vazia, `KUBECONFIG` inexistente e `MCP_SERVER_URL` inalcançável, para que nenhum acionamento escreva no cluster nem gaste API.

| Passo | Resultado |
|---|---|
| Startup com CORRIGINDO e EM_ANALISE do seed | Log: `1 EM_ANALISE -> INCOMPLETO, 1 CORRIGINDO -> FALHA_CORRECAO`; reseed depois do startup para ver os seis status |
| `/reports` | Ordem decrescente, "Análise em lote" + ID abreviado, "—" sem severidade, badge correto nos seis status |
| Link "Relatórios" no cabeçalho | Presente em todas as páginas; "Tasks" ausente |
| Detalhe COMPLETO | Metadados, `event_uids`, tabela e bloco de código renderizados; `<none>` aparece literalmente; botão presente |
| Detalhe EM_ANALISE / INCOMPLETO sem Markdown | Mensagens de estado vazio da spec |
| Detalhe CORRIGINDO / CORRIGIDO | Sem botão; CORRIGIDO exibe "Resultado da Correção" |
| Detalhe FALHA_CORRECAO | Botão presente e resultado anterior exibido |
| Clique em "Executar correção" (COMPLETO) | `303` → CORRIGINDO com `correction_started_at` → FALHA_CORRECAO (MCP inalcançável), botão volta |
| Clique numa aba com o relatório já CORRIGINDO (clique duplo simulado) | `?erro=em_andamento`, "Correção já em andamento", sem botão |
| Aba antiga de relatório já CORRIGIDO | `?erro=status_invalido`, mensagem da spec |
| UUID inexistente / id inválido | 404 com "Voltar para relatórios" / 422 do FastAPI |

Ajuste feito a partir do roteiro: o cliente MCP levanta `ExceptionGroup` ("unhandled errors in a TaskGroup"); `error_message` passou a mostrar as exceções internas no `correction_result`.

O 503 não foi exercitado no navegador (exigiria parar o PostgreSQL); está coberto pelos testes de rota com `OperationalError` e `ConnectionRefusedError`.

### Suítes (10.8) — 2026-10-18

- `uv run pytest`: 208 passed, 1 skipped (o caso parametrizado de `test_verdict.py` lido de `e2e_correction_responses.json`, que ainda não existe).
- `uv run pytest -m db`: 30 passed.
- `uv run pytest -m e2e`: 2 skipped. O contexto ativo é `kind-kind` e o cluster `aiops` não existe (`kind get clusters`). **Pendente**: rodar com o cluster `kind-aiops`, o MCP Server apontando para ele e `ANTHROPIC_API_KEY`. Isso também gera `tests/fixtures/e2e_correction_responses.json` (10.5).
