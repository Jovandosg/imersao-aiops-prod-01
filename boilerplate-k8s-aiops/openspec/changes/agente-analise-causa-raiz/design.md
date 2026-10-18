## Context

O coletor (`collector/`, capability `coleta-eventos`) despacha cada lote de Warnings como task fire-and-forget para `EventHandler.handle(events)`. Hoje esse handler é um placeholder que imprime no stdout. Os módulos `models/` e `agents/` estão vazios, não há Alembic e existem dois engines: um no nível de módulo em `database.py` e outro criado no `lifespan`. As dependências do agente (`langchain[anthropic]`, `langchain-mcp-adapters>=0.3.0`) já estão no `pyproject.toml`.

O coletor reentrega o mesmo evento em ciclos consecutivos (sobreposição de um intervalo) e, após um restart, entrega todos os Warnings vivos (~1 h). Os eventos recorrentes do kubelet chegam como legados, com recência em `deprecatedLastTimestamp` (D10 da coleta). Esta change implementa o PRD 002 inteiro, com as decisões D1–D14 daquele PRD.

Cenários de referência (`manifestos-k8s/`, cluster kind `aiops`):

| Namespace | Manifesto | Defeito | Causa raiz esperada |
|---|---|---|---|
| `teste-a` | `nginx.yaml` | imagem `ngin:latest` | imagem inexistente → `ErrImagePull`/`ImagePullBackOff` |
| `teste-b` | `kube-news.yaml` | `DB_PASSWORD=pg123`, enquanto o postgres usa `pg1234`; 10 réplicas | autenticação no banco falha → `BackOff`/CrashLoop |

## Goals / Non-Goals

**Goals:**
- Tabela `reports` versionada, com o schema final que os PRDs 002, 003 e 004 precisam.
- Deduplicação correta diante das reentregas do coletor, testável sem banco.
- Agente somente leitura que diagnostica os dois cenários de referência, validado ponta a ponta no kind.
- Um só sessionmaker na aplicação.

**Non-Goals:**
- Interface web (PRD 003) e correção (PRD 004).
- Trava atômica contra handlers concorrentes (PRD 002, decisão 6: aceito na v1).
- Saída estruturada do agente (PRD 002, D1: Markdown puro na v1).
- Teto de concorrência de análises simultâneas.

## Decisions

### D1. Layout dos módulos
```
models/
├── report.py       # Report (ORM) + ReportStatus (StrEnum)
└── repository.py   # consultas e transições (recebem AsyncSession)
agents/
├── config.py       # AGENT_MODEL_NAME, AGENT_MAX_ITERATIONS, MCP_SERVER_URL, cooldown, stale
├── dedup.py        # blocked_uids(...) — função pura
├── handler.py      # AnalysisEventHandler (implementa o Handler do coletor)
├── prompt.py       # prompt do PRD 002 + serialização dos eventos
├── parser.py       # parse_report(markdown, batch_uids) -> list[Problem] — função pura
└── analyzer.py     # RootCauseAnalyzer: MCP → tools filtradas → agente → parse → troca
```
`collector/handler.py` e `tests/test_handler.py` são removidos (requisito REMOVED na `coleta-eventos`). O protocolo `Handler` do `collector/loop.py` não muda.

### D2. Deduplicação: SQL busca os candidatos, Python decide
O bloqueio de um uid depende do `timestamp` daquele evento (regra do CORRIGIDO), então uma única cláusula `WHERE` por lote não basta.
1. **SQL**: `SELECT ... FROM reports WHERE event_uids && :uids`, usando o índice GIN e trazendo todos os status.
2. **Python**: `blocked_uids(reports, events, now, cooldown) -> set[str]`, função pura com as três regras da spec.

*Alternativa:* `unnest(:uids, :timestamps)` com `EXISTS` correlacionado. Resolve tudo no banco, mas a regra fica enterrada em SQL e só pode ser testada com PostgreSQL. O volume esperado não justifica isso.

### D3. Referência do cooldown é `created_at`
A recuperação de startup e o timeout de estagnação marcam INCOMPLETO e atualizam `updated_at`. Medir o cooldown por `updated_at` travaria todo relatório recuperado por mais 30 minutos. `created_at` (início da análise) não muda com a recuperação e também impede que um crash-loop da aplicação dispare uma análise a cada restart. O PRD 002 (US01 e D6) foi ajustado para isso.

### D4. Fluxo do handler
```
handle(events)
 └─ tx 1:  UPDATE stale EM_ANALISE → INCOMPLETO
           SELECT candidatos (&&) → blocked_uids → liberados
           liberados vazio?  → commit, log, fim
           INSERT report EM_ANALISE(event_uids=liberados) RETURNING id
           commit
 └─ analyzer.analyze(report_id, liberados)       (fora da tx; minutos)
     └─ exceção → log + mark_incomplete(report_id)   (condicional a EM_ANALISE)
```
O `now` vem de um `clock` injetável, como no `EventCollector`.

### D5. Transições condicionais
Toda transição que parte de EM_ANALISE (`mark_incomplete`, troca do lote) usa `WHERE id = :id AND status = 'EM_ANALISE'`. É o mesmo padrão que o PRD 004 usa no `/fix`. Um agente lento que termina depois da recuperação não reintroduz nada.

### D6. Contrato do Analyzer
```python
class Analyzer(Protocol):
    async def analyze(self, report_id: UUID, events: list[dict]) -> None: ...
```
O analisador é dono da finalização (troca ou INCOMPLETO) e recebe o sessionmaker no construtor. O handler só intervém quando ele lança exceção. Nos testes do handler, um fake substitui o `RootCauseAnalyzer`.

### D7. Construção do agente por análise
A cada `analyze()`: `MultiServerMCPClient({"k8s": {"transport": "http", "url": MCP_SERVER_URL}})` → `await client.get_tools()` → filtro por nome (`kubectl_get`, `kubectl_describe`, `kubectl_logs`) → `create_agent(ChatAnthropic(model=..., max_retries=3), tools, middleware=[ModelCallLimitMiddleware(run_limit=..., exit_behavior="end")])` → `ainvoke` com o prompt numa mensagem `user`. A resposta é o conteúdo de texto da última `AIMessage`.

*Por que por análise:* uma falha de conexão com o MCP vira exceção dentro do `analyze` (→ INCOMPLETO), e um MCP reiniciado volta a funcionar sem reiniciar a app. O custo de `get_tools()` é desprezível perto da análise. *Alternativa:* cliente e agente criados no `lifespan`, que exigiria o MCP de pé no startup e reconexão própria.

A filtragem fica numa função pura `select_read_only(tools)` para o teste da spec. Se alguma das três tools não existir no servidor, registrar warning e seguir com as que existem.

### D8. Parser
`parse_report(text, batch_uids) -> list[Problem]`, função pura com regex por seção:
- divide em `^## Problema \d+:\s*(.+)$`;
- campos por `^- \*\*Campo:\*\*\s*(.+)$`, tolerando maiúsculas e minúsculas e o acento em "Conclusão";
- uids por split em vírgula e espaço, com `strip` de crases.

O Markdown persistido é a seção, com o cabeçalho trocado por `# <título>`. As validações de uid seguem a spec. O parser é testado com respostas fixas, incluindo uma resposta real capturada no e2e e salva em `tests/fixtures/`.

### D9. Troca e retry
`swap_batch(session, batch_id, problems)`: um `UPDATE` condicional com `RETURNING` e um `INSERT` dos demais, numa transação. Erros de conexão do SQLAlchemy (`OperationalError`, `InterfaceError`) são repetidos 3 vezes com backoff de 1, 2 e 4 s. Esgotadas as tentativas, o erro vai para o log junto com a resposta do agente. Um `UPDATE` sem linha afetada não é erro: gera warning e o resultado é descartado.

### D10. Modelo e migration
- `id`: `UUID` com `default=uuid4` gerado na aplicação.
- `status`: `String` + `CheckConstraint` com os seis valores, e não `ENUM` nativo, para evitar `ALTER TYPE` no futuro.
- `event_uids`: `postgresql.ARRAY(Text)` + `Index(..., postgresql_using="gin")`; a consulta usa `.overlap()`.
- `created_at`/`updated_at`: `server_default=func.now()`, e `updated_at` também com `onupdate`. Os `UPDATE` em massa definem o valor explicitamente.
- Alembic com template async (`alembic init -t async alembic`), `env.py` lendo `get_database_url()` e `Base.metadata`. A migration é revisada à mão para conferir o GIN e o check.

### D11. Sessionmaker único e ordem no `lifespan`
```
lifespan:
  engine → app.state.sessionmaker
  await recover_orphans(sessionmaker)          # erro → log, segue
  analyzer = RootCauseAnalyzer(sessionmaker, agent_config)
  handler  = AnalysisEventHandler(sessionmaker, analyzer, dedup_config)
  collector = EventCollector(KubernetesEventSource(), handler, interval)
  collector.start()
```
`database.py` fica com `Base` e `get_database_url`. O grep confirma que não há outros consumidores de `engine` e `async_session`. Se `ANTHROPIC_API_KEY` estiver vazia no startup, registrar um warning claro. A app sobe mesmo assim, e cada análise falha → INCOMPLETO.

### D12. Estratégia de testes e validação ponta a ponta
| Camada | Cobre | Como | Execução |
|---|---|---|---|
| Unitário | `blocked_uids`, `parse_report`, `select_read_only`, configs, prompt, handler com fakes, ordem do `lifespan` | sem rede | `uv run pytest` |
| Banco | migration, check, overlap/GIN, stale, insert-first, `mark_incomplete`, `swap_batch` (incluindo o caso condicional), recuperação | PostgreSQL do compose, banco `aiops_k8s_test` | `uv run pytest -m db` |
| Integração kind | coleta real (já existente) | kind `aiops` | `uv run pytest -m kind` |
| **E2E automatizado** | fluxo completo nos cenários de referência | kind + PostgreSQL + MCP via npx + API Anthropic | `uv run pytest -m e2e` |
| **E2E manual** | app rodando via uvicorn, ciclos reais, restart, falhas | roteiro em `tasks.md` §9 | manual, resultado registrado aqui |

**E2E automatizado (`tests/test_e2e.py`):**
1. Pré-condições (o teste é pulado com mensagem se faltar alguma): contexto `kind-aiops`, PostgreSQL acessível, `MCP_SERVER_URL` respondendo e `ANTHROPIC_API_KEY` definida.
2. Fixture: recria os namespaces `teste-a` e `teste-b`, aplica `nginx.yaml` e `kube-news.yaml` e espera até 3 min pelos Warnings `Failed`/`BackOff` dos dois namespaces.
3. Executa o fluxo real: `KubernetesEventSource().list()` → `select_events(..., watermark=None)`, filtrado aos dois namespaces para reduzir custo e ruído → `AnalysisEventHandler(...).handle(events)` com o `RootCauseAnalyzer` real, aguardado.
4. Asserções da spec "Diagnóstico dos cenários de referência":
   - um relatório COMPLETO com `namespace=teste-a`, uid do `nginx-*` e `ngin:latest` no Markdown;
   - um relatório COMPLETO com `namespace=teste-b`, uid do `kubenews-*` e menção a senha, autenticação ou `DB_PASSWORD`;
   - todo uid entregue aparece em algum relatório.
5. Segunda chamada de `handle` com os mesmos eventos: nenhum relatório novo.
6. Salva a resposta bruta do agente em `tests/fixtures/` (só na primeira execução) para os testes do parser.

As asserções sobre texto aceitam variações ("ngin:latest" ou "ngin"; "password", "senha", "autentica" ou "DB_PASSWORD"), porque a saída do LLM não é determinística. Se o teste falhar por qualidade do diagnóstico, a primeira alavanca é ajustar o prompt e a segunda é `AGENT_MODEL_NAME` (PRD 002, D2).

## Risks / Trade-offs

- [O LLM omite ou reformata uids → evento sem relatório] → Aceito na v1 (PRD 002, D1); warning no log; o e2e mede isso no cenário real.
- [Haiku não identifica a senha divergente do kube-news, que exige ler logs e comparar envs de dois Deployments] → O e2e torna isso visível; ajustar o prompt ou subir o modelo.
- [Custo: cada `pytest -m e2e` faz uma análise real] → Lote filtrado aos dois namespaces; marker fora da execução padrão.
- [Primeira coleta após um restart entrega até ~1 h de Warnings num único lote grande] → Uma análise só, limitada por `AGENT_MAX_ITERATIONS`. Se o lote for grande demais para um bom diagnóstico, avaliar dividir por namespace (fora do escopo).
- [Handlers concorrentes podem duplicar EM_ANALISE] → Janela desprezível com ciclos de ~3 min (aceito). Endurecimento barato: `pg_advisory_xact_lock` na tx 1.
- [`timestamp` com resolução de segundos versus `corrected_at` em microssegundos] → Comparação estrita: um evento no mesmo segundo da correção conta como reentrega, que é o lado seguro.
- [Análise mais lenta que `ANALYSIS_STALE_TIMEOUT_MINUTES`] → A troca condicional descarta o resultado (D5). O timeout precisa ficar acima do pior caso, monitorado no e2e manual.

## Migration Plan

1. `docker compose up -d` e `uv run alembic upgrade head`
2. `ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes` com o contexto do cluster ativo
3. Preencher `ANTHROPIC_API_KEY` no `.env` e subir a app

Rollback: `uv run alembic downgrade base` e voltar o commit.

## Open Questions

- Nenhuma bloqueante. O resultado do e2e pode reabrir a escolha do modelo padrão.

## Resultado da validação

Executada em 2026-10-18, num cluster kind `aiops` recém-criado (`nginx.yaml` em `teste-a` e `kube-news.yaml` em `teste-b`), com PostgreSQL do compose, MCP Server via `npx` e `AGENT_MODEL_NAME=claude-haiku-4-5`. O prompt e o modelo padrão **não foram alterados**.

### Suítes automatizadas
| Suíte | Resultado |
|---|---|
| `uv run pytest` | 105 passed |
| `uv run pytest -m db` | 13 passed |
| `uv run pytest -m kind` | 5 passed |
| `uv run pytest -m e2e` | 1 passed na primeira execução (lote de 13 eventos, análise em 30,8 s, 2 relatórios COMPLETO/CRITICO) |

No e2e, o modelo listou um uid do nginx também no Problema 2. O parser o manteve só no Problema 1 (warning), e todos os uids ficaram cobertos. A resposta bruta está em `tests/fixtures/e2e_agent_response.json` e tem teste de parser próprio.

### Roteiro manual (§9, app via uvicorn, `EVENT_COLLECTION_INTERVAL_MINUTES=0.5`, `ANALYSIS_RETRY_COOLDOWN_MINUTES=2`)
| Passo | Resultado |
|---|---|
| 9.1 Startup | Log em ordem: recuperação (0 órfãos) → coletor iniciado → 1º lote (23 eventos: os dois cenários + ruído de `kube-system` do cluster novo) → relatório EM_ANALISE |
| 9.2 Relatórios | Análise em 66,8 s, 6 problemas. nginx: COMPLETO, `ngin:latest` identificado (severidade MEDIO). kube-news: **INCOMPLETO** na primeira tentativa (o `kubectl_logs` falhou com "unable to retrieve container logs" e o agente não tentou outro pod nem comparou os envs) |
| 9.3 Reentrega | Ciclos seguintes com todos os eventos bloqueados (`N recebido(s), N bloqueado(s), relatorio nao criado`) |
| 9.4 Cooldown | O INCOMPLETO do kube-news (criado às 19:31:20 UTC) ficou bloqueado nos ciclos dentro do cooldown e foi reanalisado às 19:33:43: **COMPLETO/CRITICO, "Falha de Autenticação PostgreSQL - Mismatch de Senha"** (26,0 s). O uid que o modelo deixou sem citar foi reanalisado sozinho, também com o diagnóstico de senha |
| 9.5 MCP fora | `kubectl scale deploy/nginx --replicas=2` com o MCP parado: erro no log (ExceptionGroup de conexão), relatório INCOMPLETO e loop vivo |
| 9.6 Restart | Ctrl+C com um relatório EM_ANALISE; no restart, `Recuperacao de analises orfas: 1 relatorio(s)` antes da primeira coleta, e o relatório ficou INCOMPLETO |
| 9.7 Banco fora | `docker compose stop postgres`: `Banco indisponivel na deduplicacao; lote ... descartado` a cada ciclo, loop vivo; depois de religar, o ciclo seguinte criou relatório normalmente |

**Tempos de análise:** 12–67 s (mediana ~20 s). O pior caso fica muito abaixo do `ANALYSIS_STALE_TIMEOUT_MINUTES` padrão (30 min).
**Custo:** não medido (a app não registra uso de tokens). Ver o console da Anthropic para o período do teste.

### Relatório de referência (nginx, trecho)
```markdown
# Image Pull Error - imagem não encontrada (teste-a/nginx)
- **Severidade:** MEDIO
- **Namespace:** teste-a
- **Recursos Afetados:** pod/nginx-86857974b8-d4cbg
- **Eventos:** 51a29f5c-..., 0e7c76ba-..., 6a5e0bf8-...
- **Conclusao:** conclusiva

### Causa Raiz
O deployment `nginx` em teste-a tenta pullar a imagem `ngin:latest` (nome com typo - falta 'x')...
```
O relatório de referência do kube-news (senha `pg123` × `pg1234`, erro 28P01 nos logs) está na fixture do e2e.

### Observações
- Com o lote ruidoso do primeiro ciclo, o Haiku não fechou o kube-news de primeira; o cooldown do INCOMPLETO resolveu na tentativa seguinte. Se isso se repetir, a primeira alavanca é o prompt (orientar a tentar `kubectl_logs` sem `previous` ou em outro pod e a comparar os envs com o Deployment da dependência). A segunda é o modelo.
- A severidade varia entre execuções (nginx saiu CRITICO no e2e e MEDIO no roteiro manual).
- Retry da gravação: 3 tentativas com espera de 1 s e 2 s entre elas. O "4 s" da D9 sobraria, porque não há uma quarta tentativa.
