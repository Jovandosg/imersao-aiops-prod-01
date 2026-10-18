---
prd_number: "002"
status: rascunho
priority: alta
created: 2026-06-16
issue:
depends_on: ["001"]
references: ["003", "004"]
---

# PRD 002: Agente de Analise de Causa Raiz e Geracao de Relatorio

## 1. Contexto

- **Sistema/produto**: Agente AIOps para Kubernetes — aplicacao Python com FastAPI, LangChain, Claude Sonnet e MCP Server Kubernetes. O PRD 001 implementa a coleta periodica de eventos Warning do cluster.
- **Estado atual**: Eventos sao coletados automaticamente (PRD 001), mas nao ha analise automatizada. O diagnostico de causa raiz e manual, dependente da experiencia do operador, e nao produz documentacao estruturada. Problemas recorrentes sao reinvestigados do zero.
- **Problema**: O tempo de diagnostico e alto (30min-2h) e varia com a experiencia do operador. Nao ha registro padronizado do processo de troubleshooting, dificultando a transferencia de conhecimento. Eventos ja em tratamento podem ser reprocessados desnecessariamente, desperdicando recursos de API e gerando relatorios duplicados.

## 2. Solucao Proposta

### Visao geral

- Implementa o `EventHandler` do PRD 001, recebendo lista de eventos no contrato de saida definido naquele PRD
- Filtra os eventos que ja estao em tratamento (deduplicacao por `metadata.uid` do evento Kubernetes)
- Agente construido com LangChain + Claude Sonnet usando loop de tool-calling (estilo ReAct, via `create_agent`) investiga a causa raiz
- O agente se conecta ao cluster via MCP Server Kubernetes (Flux159) para inspecionar o estado dos recursos, utilizando o pacote `langchain-mcp-adapters` para integracao; apenas as tools de leitura (`kubectl_get`, `kubectl_describe`, `kubectl_logs`) sao vinculadas ao agente
- Gera um relatorio Markdown estruturado por problema agrupado, com severidade, causa raiz, evidencias, comandos executados e passos de correcao
- Persiste cada relatorio no PostgreSQL com status e referencia aos UIDs dos eventos daquele problema

### Decisoes-chave

1. **LangChain como framework de agente** — Abstracoes prontas para ReAct, integracao com MCP via pacote `langchain-mcp-adapters` e gerenciamento de tools
2. **Claude como LLM (default `claude-haiku-4-5`)** — Modelo configuravel via `AGENT_MODEL_NAME`; o padrao Haiku prioriza custo/velocidade para troubleshooting, com modelos classe Sonnet como override opcional para casos que exijam mais raciocinio (ver §9, decisao D2)
3. **MCP Server Kubernetes (Flux159)** — Servidor MCP existente para interacao com o cluster, evitando implementacao propria
4. **Loop de tool-calling (estilo ReAct)** — Permite iteracao entre analise e acao ate encontrar a causa raiz real; o `create_agent` implementa tool-calling nativo da API
5. **Deduplicacao por `metadata.uid` com predicado temporal** — Eventos ja vinculados a relatorios ativos sao ignorados; eventos vinculados a relatorios CORRIGIDO sao reanalisados apenas se observados **apos** a correcao (`timestamp` do evento > `corrected_at`), e eventos vinculados a relatorios INCOMPLETO apenas apos um cooldown (`ANALYSIS_RETRY_COOLDOWN_MINUTES`). O predicado temporal e necessario porque o coletor (PRD 001) reentrega o mesmo evento em ciclos consecutivos (janela com sobreposicao) e na primeira coleta apos restart (sem filtro) — status sozinho nao distingue reincidencia real de reentrega (ver §9, decisoes D5 e D6). Limitacao conhecida: o EventAggregator do Kubernetes pode criar novos objetos Event com UIDs diferentes para o mesmo problema logico em alta frequencia (10+ ocorrencias em 10 minutos). Risco aceito na v1.
6. **Status EM_ANALISE para evitar race condition** — O relatorio e criado com status EM_ANALISE como **primeira operacao do tratamento, antes da chamada ao agente** (insert-first), garantindo que despachos concorrentes (tasks assincronas do PRD 001 que se sobrepoem) e a recuperacao de crash identifiquem os eventos como "em tratamento" e nao disparem analise duplicada. Com intervalo de coleta de ~3 min e ciclos de coleta serializados, a gravacao antecipada do EM_ANALISE dispensa trava de concorrencia (insert atomico/constraint) na v1; a trava atomica fica registrada como endurecimento futuro (intervalo muito menor ou re-disparo manual/externo)
7. **Somente tools de leitura vinculadas ao agente** — A lista de tools retornada pelo `langchain-mcp-adapters` e filtrada para expor apenas `kubectl_get`, `kubectl_describe` e `kubectl_logs`; tools de escrita do MCP Server nao chegam ao agente de analise
8. **Um relatorio por problema agrupado** — Cada problema identificado pelo agente vira um relatorio proprio com seus event_uids, permitindo acompanhar e corrigir cada incidente ate a resolucao de forma independente (status e correcao nos PRDs 003/004 operam por relatorio)
9. **Metadados do problema como colunas** — Severidade, namespace, titulo e conclusao sao extraidos no mesmo parse que mapeia os event_uids e gravados em colunas; consumidores (PRD 003) nao fazem parse do Markdown (ver §9, decisao D8)

### Fora do escopo

- **Coleta de eventos** — Responsabilidade do PRD 001
- **Interface de visualizacao dos relatorios** — Responsabilidade do PRD 003
- **Execucao da correcao** — Responsabilidade do PRD 004
- **Historico de eventos brutos no banco** — Apenas relatorios sao persistidos

## 3. Funcionalidades

### US01: Filtragem de eventos ja em tratamento

Como SRE, quero que eventos ja vinculados a um relatorio ativo nao sejam reanalisados, para evitar relatorios duplicados e desperdicio de recursos de API.

**Rules:**
- Antes de disparar a analise, verificar se os `metadata.uid` dos eventos ja estao vinculados a relatorios existentes
- Eventos vinculados a relatorios com status EM_ANALISE, COMPLETO, CORRIGINDO ou FALHA_CORRECAO sao ignorados
- Eventos vinculados a relatorios CORRIGIDO sao reanalisados **somente se** o `timestamp` do evento (recencia do contrato do PRD 001) for posterior ao `corrected_at` do relatorio — reincidencia real; reentrega do mesmo evento antigo (sobreposicao da janela ou primeira coleta apos restart) e ignorada (ver §9, decisao D5)
- Eventos vinculados a relatorios INCOMPLETO sao reanalisados **somente se** `now - created_at` do relatorio (inicio da analise) exceder `ANALYSIS_RETRY_COOLDOWN_MINUTES` (padrao: 30); antes disso sao ignorados — evita reanalise a cada ciclo de eventos com `series` ativa. A referencia e `created_at`, nao `updated_at`, porque a recuperacao de startup e o timeout de estagnacao atualizam `updated_at` ao marcar INCOMPLETO e travariam o evento por mais um cooldown inteiro (ver §9, decisao D6)
- Predicado de reanalise de um uid: nao existe relatorio ativo com o uid **E** (nao existe relatorio algum com o uid **OU** existe CORRIGIDO com `timestamp > corrected_at` **OU** existe INCOMPLETO com cooldown vencido). Relatorio CORRIGIDO/INCOMPLETO que nao satisfaz sua condicao temporal bloqueia o uid como se fosse ativo
- A consulta de deduplicacao avalia a EXISTENCIA de qualquer relatorio ativo contendo o uid (overlap de arrays `event_uids && :uids` filtrado por status IN {EM_ANALISE, COMPLETO, CORRIGINDO, FALHA_CORRECAO}), **nunca** o status do relatorio mais recente: se ao menos um relatorio ativo contem o uid, o evento e ignorado — mesmo que exista tambem um relatorio antigo em CORRIGIDO/INCOMPLETO com o mesmo uid (ver §9, decisao D4)
- A tabela de relatorios armazena o campo `event_uids` (`TEXT[]` com GIN index — lista de UIDs dos eventos Kubernetes analisados)
- Relatorios em EM_ANALISE ha mais de `ANALYSIS_STALE_TIMEOUT_MINUTES` minutos (padrao: 30) sao marcados como INCOMPLETO durante a consulta de deduplicacao — recuperacao de analises estagnadas, complementar a recuperacao do startup
- `ANALYSIS_RETRY_COOLDOWN_MINUTES` e `ANALYSIS_STALE_TIMEOUT_MINUTES` com valor invalido (nao-numerico, negativo ou zero) → usar o padrao e registrar warning no log

**Edge cases:**
- Todos os eventos do batch ja estao em tratamento → nao disparar analise, aguardar proximo ciclo
- Parte dos eventos do batch ja esta em tratamento → filtrar e analisar apenas os novos
- Evento reaparece apos relatorio marcado como CORRIGIDO, com `timestamp` posterior a `corrected_at` → reanalisar e gerar novo relatorio
- Mesmo evento reentregue logo apos a correcao (sobreposicao da janela de coleta ou restart), com `timestamp` anterior a `corrected_at` → ignorar
- Evento de relatorio INCOMPLETO reentregue antes do fim do cooldown → ignorar; apos o cooldown → reanalisar
- Banco de dados indisponivel para consulta de deduplicacao → registrar erro no log e descartar o batch; como o despacho do PRD 001 e assincrono (fire-and-forget), nao ha propagacao ao coletor nem hold de marca d'agua. Evento recorrente volta no proximo ciclo; evento one-shot e perdido (risco aceito na v1)

### US02: Analise automatizada de causa raiz

Como SRE, quero que um agente de IA investigue automaticamente a causa raiz dos eventos coletados, para reduzir o tempo de diagnostico e nao depender da experiencia individual de cada operador.

**Rules:**
- O agente e construido com LangChain + Claude em loop de tool-calling (estilo ReAct), via `create_agent` de `langchain.agents`
- O modelo e configuravel via variavel de ambiente `AGENT_MODEL_NAME` (padrao: `claude-haiku-4-5`)
- O agente se conecta ao cluster via MCP Server Kubernetes (Flux159), utilizando `langchain-mcp-adapters` para converter tools MCP em tools LangChain; o servidor e executado localmente via `npx` expondo transport HTTP (streamable), e o agente conecta com `transport: "http"` (nome canonico atual do `langchain-mcp-adapters`; `streamable_http` e alias legado) em `MCP_SERVER_URL` (padrao `http://localhost:3001/mcp`)
- Apenas as tools de leitura `kubectl_get`, `kubectl_describe` e `kubectl_logs` sao vinculadas ao agente — a lista retornada pelo `langchain-mcp-adapters` e filtrada por nome antes da criacao do agente; tools de escrita (`kubectl_apply`, `kubectl_patch`, `kubectl_delete`, etc.) nao sao expostas
- A investigacao segue o ciclo: analise → acao → reflexao → proxima acao
- O agente itera ate identificar a causa raiz ou atingir o limite de iteracoes, configuravel via variavel de ambiente `AGENT_MAX_ITERATIONS` (padrao: 25), implementado com `ModelCallLimitMiddleware(run_limit, exit_behavior="end")` no `create_agent`. Com `exit_behavior="end"` o run encerra graciosamente sem uma chamada extra ao modelo — nao ha relatorio parcial garantido; a resposta final (possivelmente vazia ou sem secoes de problema identificaveis) mantem o relatorio do batch como INCOMPLETO (ver US03 edge cases)
- O agente deve investigar o estado dos recursos relacionados ao evento (pod, deployment, node, etc.)

**Prompt do agente:**

```
Voce e um analista especializado em diagnostico Kubernetes. Sua funcao e investigar e identificar problemas usando as ferramentas disponiveis.

Voce recebeu os seguintes eventos Warning coletados do cluster:

{events}

## REGRAS
- Apenas diagnostica e sugere correcoes. NUNCA execute kubectl_patch, kubectl_apply ou kubectl_delete.
- Use APENAS os parametros documentados das tools.
- Investigue por PROBLEMA AGRUPADO, nao por evento individual.
- Se ja tiver causa raiz + evidencias suficientes, passe ao proximo problema.
- NUNCA chame a mesma ferramenta com os mesmos parametros duas vezes.
- Em **Eventos**, liste o uid de CADA evento recebido em exatamente um problema.
- Em **Conclusao**, use "inconclusiva" se nao reuniu evidencias suficientes para afirmar a causa raiz.

## COMO INVESTIGAR
Voce tem 3 ferramentas de leitura. Use-as IMEDIATAMENTE para coletar evidencias:
- **kubectl_get**: visao geral dos recursos (status, restarts, idade). Use `name` OU `labelSelector`, NUNCA ambos juntos.
- **kubectl_describe**: detalhes completos (eventos, conditions, configuracao).
- **kubectl_logs**: logs do container. Use `previous: true` para logs de execucao anterior.

Para cada problema recebido:
1. Chame kubectl_describe no recurso afetado para obter detalhes
2. Se necessario, chame kubectl_logs para ver erros da aplicacao
3. Com as evidencias coletadas, escreva o relatorio

## TRATAMENTO DE ERROS
- "name cannot be provided when a selector is specified" -> Use APENAS name OU labelSelector
- Se uma ferramenta falhar 2 vezes, registre o erro como evidencia e prossiga

## SEVERIDADE
- **CRITICO**: Pod/Deployment indisponivel, servico fora do ar
- **ALTO**: Restarts frequentes, OOMKilled, recursos esgotados
- **MEDIO**: Warnings recorrentes mas servico funcional
- **BAIXO**: Eventos informativos, problemas cosmeticos

## FORMATO DE RESPOSTA (Markdown)

# Relatorio de Diagnostico Kubernetes

## Resumo
| Total | Criticos | Altos | Medios | Baixos |
|-------|----------|-------|--------|--------|
| X     | X        | X     | X      | X      |

---

## Problema 1: [causa raiz resumida]
- **Severidade:** CRITICO | ALTO | MEDIO | BAIXO
- **Namespace:** namespace-afetado
- **Recursos Afetados:** pod1, deployment/nome
- **Eventos:** uid-evento-1, uid-evento-2
- **Conclusao:** conclusiva | inconclusiva

### Causa Raiz
Descricao clara do problema.

### Evidencias
- evidencia 1
- evidencia 2

### Solucao Recomendada
Acao especifica para corrigir.

### Comando Sugerido
kubectl patch deployment nome -n namespace --type=strategic -p '{"spec":...}'

Repita a secao para cada problema. Responda APENAS com o relatorio markdown.
```

**Edge cases:**
- MCP Server Kubernetes indisponivel → abortar analise, atualizar relatorio para INCOMPLETO e registrar erro no log; sem propagacao ao coletor (despacho assincrono do PRD 001). Recuperacao via dedup-reanalise na recorrencia do evento (eventos vinculados a INCOMPLETO sao reanalisados, US01) + recovery de startup/stale; evento one-shot que nao recorre e perdido (risco aceito na v1)
- Agente atinge limite de iteracoes sem identificar causa raiz → se a resposta final contiver secoes de problema, cada problema com `**Conclusao:** inconclusiva` vira relatorio INCOMPLETO; se nao contiver secoes, o relatorio do batch e marcado INCOMPLETO (US03)
- Erro na API do Claude (rate limit, timeout) → retry automatico do SDK com backoff exponencial (`max_retries=3` no `ChatAnthropic`); esgotadas as tentativas, abortar, atualizar relatorio para INCOMPLETO e registrar erro, sem propagacao ao coletor (despacho assincrono do PRD 001)
- Evento ja corrigido entre a coleta e a analise → agente identifica estado saudavel e registra no relatorio
- Variavel de ambiente `AGENT_MAX_ITERATIONS` com valor invalido (nao-numerico, negativo ou zero) → usar o padrao de 25 iteracoes e registrar warning no log

### US03: Geracao e persistencia de relatorio estruturado

Como SRE, quero que cada investigacao produza um relatorio Markdown estruturado e persistido, para ter documentacao padronizada de troubleshooting e facilitar a transferencia de conhecimento.

**Rules:**
- A resposta do agente segue a estrutura definida no prompt: resumo com contagem por severidade e uma secao por problema (severidade, namespace, recursos afetados, eventos, causa raiz, evidencias, solucao recomendada e comando sugerido)
- Cada secao de problema e persistida como um relatorio proprio no PostgreSQL, com ID unico e os event_uids dos eventos daquele problema (mapeados pelo campo **Eventos** da resposta)
- O conteudo Markdown de cada relatorio por problema e **apenas a secao daquele problema**, com o titulo promovido de `## Problema N: <causa>` para `# <causa>`; a tabela de Resumo (que descreve o batch) nao e persistida (ver §9, decisao D9)
- No mesmo parse, cada secao fornece as colunas `severity` (CRITICO/ALTO/MEDIO/BAIXO), `namespace`, `title` (causa raiz resumida do titulo) e o status: `**Conclusao:** conclusiva` → COMPLETO; `inconclusiva` → INCOMPLETO. Campo ausente ou valor desconhecido → COMPLETO com warning no log; severidade ausente ou desconhecida → `severity` NULL com warning
- Validacao dos uids citados no campo **Eventos**: apenas uids pertencentes ao batch sao aceitos (uid fora do batch → descartado com warning); uid citado em mais de um problema fica no primeiro problema em que aparece (warning); problema que fica sem nenhum uid valido e persistido com `event_uids` vazio e warning (ver §9, decisao D10)
- Durante a analise existe um unico relatorio EM_ANALISE por batch (com todos os event_uids); ao final, ele e substituido pelo conjunto de relatorios por problema na mesma transacao: o **proprio relatorio do batch e atualizado para virar o Problema 1** (preserva o ID e o link aberto na interface) e os Problemas 2..N sao inseridos como novos relatorios. A substituicao e **condicional ao status**: `UPDATE ... WHERE id = :batch_id AND status = 'EM_ANALISE' RETURNING id`; se nenhuma linha for atualizada (ja transicionado para INCOMPLETO pelo timeout de estagnacao ou pela recuperacao de startup), a transacao e abortada, nenhum relatorio e inserido e o resultado do agente e descartado (ver §9, decisoes D3 e D7)
- A tabela de relatorios armazena: id (`UUID`), conteudo markdown (`TEXT NULL` — vazio enquanto EM_ANALISE ou em INCOMPLETO de batch), status, event_uids (`TEXT[]` com GIN index), `severity` (`TEXT NULL`), `namespace` (`TEXT NULL`), `title` (`TEXT NULL`), `created_at`, `updated_at`, `corrected_at` (`TIMESTAMPTZ NULL` — preenchido pelo PRD 004 na transicao para CORRIGIDO) e `correction_result` (`TEXT NULL` — preenchido pelo PRD 004). As colunas do PRD 004 entram ja na migration inicial (ver §9, decisao D11)
- Status possiveis do relatorio: EM_ANALISE, COMPLETO, INCOMPLETO, CORRIGINDO, CORRIGIDO, FALHA_CORRECAO
- Fluxo de status: EM_ANALISE → COMPLETO (analise OK) | INCOMPLETO (analise inconclusiva ou abortada por falha de infraestrutura); COMPLETO → CORRIGINDO → CORRIGIDO | FALHA_CORRECAO; FALHA_CORRECAO → CORRIGINDO (nova tentativa de correcao, PRD 004 — FALHA_CORRECAO nao e terminal)
- Relatorios em EM_ANALISE encontrados no startup da aplicacao sao marcados como INCOMPLETO (recuperacao de analises interrompidas por crash/restart). A recuperacao e **aguardada no `lifespan` antes de `collector.start()`**: a primeira coleta do PRD 001 nao tem filtro temporal e, se rodasse antes, a deduplicacao trataria relatorios orfaos ainda em EM_ANALISE como ativos e ignoraria eventos que deveriam ser liberados (ver §9, decisao D12)
- O acesso ao banco usa um unico `async_sessionmaker`, criado no `lifespan` e exposto em `app.state.sessionmaker`; o `EventHandler` o recebe por injecao no construtor (mesmo padrao do PRD 004). O engine em nivel de modulo de `database.py` e removido (`database.py` mantem apenas `Base` e `get_database_url`) (ver §9, decisao D13)

**Edge cases:**
- PostgreSQL indisponivel no momento da persistencia → retry com backoff; apos falha definitiva, registrar erro no log incluindo o conteudo Markdown gerado (sem fallback em arquivo); sem propagacao ao coletor (despacho assincrono do PRD 001). O relatorio EM_ANALISE estagnado e recuperado pelo timeout da deduplicacao (stale) ou no startup; evento one-shot afetado e perdido (risco aceito na v1)
- Resposta do agente vazia ou sem secoes de problema identificaveis (falha do LLM) → manter o relatorio EM_ANALISE do batch como INCOMPLETO para rastreabilidade
- Dois relatorios gerados simultaneamente para eventos relacionados → cada um recebe ID proprio; deduplicacao por `event_uids` impede reanalise nos ciclos futuros
- Aplicacao reinicia durante uma analise → relatorio orfao em EM_ANALISE e marcado como INCOMPLETO no startup, liberando os eventos para reanalise
- Evento do batch nao referenciado no campo **Eventos** de nenhum problema da resposta → registrar warning no log; o evento fica sem relatorio proprio e sera reanalisado apenas se recorrer (recoletado em um ciclo futuro)
- Uid citado que nao pertence ao batch → descartado com warning (nao entra em `event_uids`)
- Mesmo uid citado em dois problemas → mantido apenas no primeiro, com warning
- Usuario com o detalhe do relatorio do batch aberto durante a analise → apos a substituicao, o mesmo ID passa a exibir o Problema 1 (sem 404); os demais problemas aparecem como novos itens na listagem

## 4. Visao de Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Pipeline de Analise                    │
│                                                          │
│  Eventos (PRD 001 via EventHandler)                      │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────────────┐    ┌──────────────┐                │
│  │ Filtro de        │───▶│ PostgreSQL   │                │
│  │ Reprocessamento  │◀───│ (event_uids) │                │
│  │ (dedup por UID)  │    └──────────────┘                │
│  └────────┬─────────┘                                    │
│           │ eventos novos                                │
│           ▼                                              │
│  ┌──────────────────────┐    ┌──────────────┐            │
│  │ Criar relatorio      │───▶│ PostgreSQL   │            │
│  │ status: EM_ANALISE   │    │ (relatorios) │            │
│  └────────┬─────────────┘    └──────────────┘            │
│           │                                              │
│           ▼                                              │
│  ┌─────────────────────┐                                 │
│  │  Agente de Analise  │                                 │
│  │ (LangChain + Claude)│                                 │
│  │  Padrao ReAct       │                                 │
│  └────────┬────────────┘                                 │
│           │ MCP (via langchain-mcp-adapters)              │
│           ▼                                              │
│  ┌────────────────┐                                      │
│  │ MCP Server K8s │──▶ Cluster K8s                       │
│  │ (Flux159)      │                                      │
│  └────────────────┘                                      │
│           │                                              │
│           ▼                                              │
│  ┌─────────────────────┐    ┌──────────────┐             │
│  │ Persistir relatorios │───▶│ PostgreSQL   │             │
│  │ por problema (US03)  │    │ (relatorios) │             │
│  └─────────────────────┘    └──────────────┘             │
└─────────────────────────────────────────────────────────┘
```

## 5. Criterios de Aceite

### Tecnicos

| Criterio | Metodo de verificacao |
|----------|----------------------|
| Eventos com UID ja vinculado a relatorio ativo sao ignorados | Teste automatizado com eventos duplicados e relatorios em diferentes status |
| Eventos vinculados a relatorio CORRIGIDO sao reanalisados apenas com `timestamp` > `corrected_at` | Teste automatizado com o mesmo uid antes e depois de `corrected_at` (reentrega ignorada, reincidencia reanalisada) |
| Eventos vinculados a relatorio INCOMPLETO respeitam o cooldown | Teste automatizado com `created_at` dentro e fora de `ANALYSIS_RETRY_COOLDOWN_MINUTES`, incluindo relatorio recuperado no startup |
| Recuperacao de startup roda antes da primeira coleta | Teste do `lifespan` validando a ordem recuperacao → `collector.start()` |
| Substituicao preserva o ID do relatorio do batch como Problema 1 | Teste com batch de dois problemas: ID original atualizado + um novo relatorio inserido |
| Colunas `severity`, `namespace`, `title` e status por problema sao extraidos da resposta | Teste de parse com secoes conclusiva/inconclusiva e severidade ausente |
| Uids fora do batch ou duplicados entre problemas sao tratados | Teste de parse com uid estranho e uid repetido |
| Relatorio e criado com status EM_ANALISE antes de iniciar investigacao | Teste automatizado validando que ciclo subsequente ignora eventos em analise |
| Agente conecta ao cluster via MCP e executa pelo menos uma iteracao ReAct | Teste de integracao com cluster de teste e evento simulado |
| Relatorio segue a estrutura definida no prompt (resumo, severidade, causa raiz, evidencias, solucao) | Validacao de schema do Markdown via teste automatizado |
| Relatorio e persistido no PostgreSQL com ID unico e event_uids | Teste de integracao com banco de dados |
| Cada problema do batch gera um relatorio proprio com seus event_uids | Teste com batch contendo dois problemas independentes validando a criacao de dois relatorios |
| Relatorio EM_ANALISE estagnado alem do timeout e marcado INCOMPLETO na deduplicacao | Teste automatizado com relatorio EM_ANALISE antigo e nova consulta de deduplicacao |
| Relatorio inconclusivo e persistido com status INCOMPLETO | Teste com cenario onde o agente atinge limite de iteracoes |
| Eventos vinculados a relatorio INCOMPLETO sao reanalisados apos o cooldown | Teste automatizado simulando analise inconclusiva seguida de recorrencia (recoleta) dos eventos apos `ANALYSIS_RETRY_COOLDOWN_MINUTES` |
| Relatorios EM_ANALISE orfaos sao marcados como INCOMPLETO no startup | Teste automatizado simulando restart com relatorio em EM_ANALISE |
| Agente possui apenas tools de leitura vinculadas (kubectl_get, kubectl_describe, kubectl_logs) | Teste automatizado inspecionando a lista de tools do agente |
| Limite de iteracoes e configuravel via `AGENT_MAX_ITERATIONS` | Teste variando o valor da env var e validando comportamento |

### De negocio

| Metrica | Baseline (fonte) | Meta | Prazo | Min. aceitavel | Responsavel |
|---------|-------------------|------|-------|-----------------|-------------|
| Tempo medio de diagnostico (da recepcao do evento ao relatorio) | 30min-2h manual (estimativa do time de SRE) | < 10 minutos | 30 dias apos deploy | < 20 minutos | Time de SRE |
| Taxa de identificacao correta da causa raiz | N/A — nao ha processo estruturado hoje | > 70% | 30 dias apos deploy | > 50% | Time de SRE |

## 6. Milestones

### Milestone 1: Implementar Filtragem de Reprocessamento

**Objetivo:** Garantir que eventos ja em tratamento nao sejam reanalisados.

**Funcionalidades:** US01, US03 (modelo de dados)

- [ ] Configurar Alembic (async) no projeto (US03)
- [ ] Unificar o acesso ao banco em `app.state.sessionmaker` e remover o engine de modulo de `database.py` (US03)
- [ ] Modelar tabela de relatorios no PostgreSQL com a migration inicial (id `UUID`, markdown, status, event_uids `TEXT[]` com GIN index, `severity`, `namespace`, `title`, `created_at`, `updated_at`, `corrected_at`, `correction_result`) (US03)
- [ ] Implementar consulta de deduplicacao por `event_uids` com o predicado temporal (CORRIGIDO por `corrected_at`, INCOMPLETO por `ANALYSIS_RETRY_COOLDOWN_MINUTES`) (US01)
- [ ] Implementar logica de filtragem antes de disparar analise (US01)
- [ ] Implementar criacao de relatorio com status EM_ANALISE antes de iniciar investigacao (US01, US03)
- [ ] Implementar recuperacao no startup, aguardada no `lifespan` antes de `collector.start()`: marcar relatorios EM_ANALISE orfaos como INCOMPLETO (US01, US03)
- [ ] Implementar timeout de estagnacao de EM_ANALISE na consulta de deduplicacao (`ANALYSIS_STALE_TIMEOUT_MINUTES`) (US01)

**Criterio de conclusao:**
- Condicao: Eventos duplicados sao corretamente filtrados com base no status dos relatorios existentes, incluindo EM_ANALISE
- Verificacao: Teste automatizado com cenarios de deduplicacao (evento novo, evento em analise, evento em tratamento, evento corrigido que reincide, evento corrigido reentregue sem reincidencia, INCOMPLETO dentro e fora do cooldown)
- Aprovador: Time de SRE

> Sequencia de entrega: o Milestone 1 fecha o modelo de dados consumido pelo PRD 003, que pode ser entregue em paralelo ao Milestone 2 usando relatorios seed (ver §9, decisao D14).

### Milestone 2: Implementar Agente de Analise

**Objetivo:** Agente investiga causa raiz automaticamente e gera relatorio estruturado.

**Funcionalidades:** US02, US03

- [ ] Implementar `EventHandler` do PRD 001 como ponto de entrada do pipeline de analise (US02)
- [ ] Configurar LangChain com Claude (`AGENT_MODEL_NAME`, padrao `claude-haiku-4-5`; Sonnet como override opcional) em loop de tool-calling via `create_agent` de `langchain.agents` (US02)
- [ ] Configurar MCP Server Kubernetes (Flux159) via `langchain-mcp-adapters` (MCP executado via npx com transport HTTP/streamable, conexao `transport: "http"` em `MCP_SERVER_URL`), filtrando apenas as tools de leitura kubectl_get, kubectl_describe e kubectl_logs (US02)
- [ ] Implementar logica de investigacao iterativa com limite de iteracoes configuravel via `AGENT_MAX_ITERATIONS`, usando `ModelCallLimitMiddleware` (US02)
- [ ] Gerar relatorios Markdown por problema seguindo a estrutura do prompt (apenas a secao do problema, titulo promovido), com mapeamento de event_uids pelo campo **Eventos** validado contra o batch (US03)
- [ ] Extrair `severity`, `namespace`, `title` e status por problema (campo **Conclusao**) no parse (US03)
- [ ] Substituir o relatorio EM_ANALISE do batch pelos relatorios por problema: UPDATE condicional do relatorio do batch como Problema 1 + INSERT dos demais, na mesma transacao (US03)
- [ ] Configurar `max_retries=3` no `ChatAnthropic` (retry com backoff nativo do SDK) (US02)

**Criterio de conclusao:**
- Condicao: Dado um evento Warning, o agente investiga via MCP, identifica causa raiz e atualiza relatorio estruturado no banco
- Verificacao: Teste de integracao end-to-end com cluster de teste e evento Warning simulado
- Aprovador: Time de SRE

## 7. Riscos e Dependencias

| Risco | Impacto | Mitigacao | Status |
|-------|---------|-----------|--------|
| Qualidade da analise do LLM pode variar — causa raiz incorreta | Alto | Monitorar taxa de acerto e iterar nos prompts. Relatorio disponivel para revisao humana | Pendente |
| Custo de API do Claude pode escalar com volume alto de eventos e investigacoes longas | Medio | Monitorar uso de tokens. Limitar iteracoes do agente via `AGENT_MAX_ITERATIONS` | Pendente |
| MCP Server Kubernetes pode nao suportar todas as operacoes necessarias | Medio | Validar operacoes necessarias contra a API do MCP Server antes do desenvolvimento. Operacoes de leitura (kubectl_get, kubectl_describe, kubectl_logs) confirmadas como suportadas | Pendente |
| EventAggregator do Kubernetes cria novos Event objects com UIDs diferentes para o mesmo problema logico em alta frequencia (10+ ocorrencias em 10 min) | Baixo | Risco aceito na v1. Deduplicacao por `metadata.uid` nao colapsara eventos agregados. Mitigacao futura: deduplicar por `involvedObject` + `reason` + `namespace` | Aceito |
| Reanalise recorrente de incidentes com relatorio INCOMPLETO consome tokens a cada recorrencia (recoleta) dos eventos — eventos com `series` ativa sao reentregues a cada ciclo | Medio | Cooldown `ANALYSIS_RETRY_COOLDOWN_MINUTES` (padrao 30) limita a no maximo uma reanalise por janela de cooldown (decisao D6). Mitigacao futura: limite de reanalises por incidente | Mitigado |
| Dedup depende da formatacao correta do campo **Eventos** pelo LLM (saida markdown pura, sem schema tipado) — se o modelo omitir ou reformatar um uid, o mapeamento uid->problema vaza e o evento fica sem relatorio proprio | Medio | Risco aceito na v1 (decisao D1, §9): markdown puro pela simplicidade. Prompt exige listar o uid de CADA evento em exatamente um problema; evento nao referenciado gera warning e e reanalisado se recorrer. Mitigacao futura: saida estruturada (`ProviderStrategy`) para os campos de mapeamento | Aceito |

**Dependencias:**

| Dependencia | Tipo | Status | Impacto se bloqueado |
|-------------|------|--------|----------------------|
| PRD 001 — Coleta de eventos (contrato de saida e `EventHandler`) | Interna | Em desenvolvimento | Sem eventos coletados, nao ha o que analisar |
| LangChain (`langchain` + `langchain-anthropic` + `langgraph`) | Externa | Disponivel | Framework base do agente |
| `langchain-mcp-adapters` (>=0.3.0) | Externa | Disponivel | Integracao entre LangChain e MCP Server. Piso >=0.3.0: `handle_tool_errors=True` (default) faz erro de EXECUCAO de tool (ex.: params invalidos, recurso ausente) retornar ao modelo como `ToolMessage(status="error")` para auto-correcao; versoes anteriores lancam `ToolException` e quebram o loop. Falhas de transporte/sessao (ex.: MCP Server indisponivel) SEMPRE levantam excecao, independente do flag — tratadas pelo handler como abort -> INCOMPLETO |
| MCP Server Kubernetes (Flux159) | Externa | Disponivel | Sem MCP, agente nao interage com o cluster |
| Node.js + npx (runtime do MCP Server Kubernetes, executado localmente com transport HTTP) | Externa | A provisionar | Sem o runtime Node, o MCP server nao inicia |
| API Claude (Anthropic) | Externa | Disponivel | Sem LLM, agente nao funciona |
| Instancia PostgreSQL | Interna | A provisionar | Sem banco, relatorios nao sao persistidos |
| Driver PostgreSQL para Python (`asyncpg`) | Externa | Disponivel | Sem driver, aplicacao nao conecta ao banco |

## 8. Referencias

- [PRD 001 - Coleta de Eventos](./001-coleta-eventos-kubernetes.md) — fornece os eventos consumidos por este PRD (contrato de saida e `EventHandler`)
- [PRD 003 - Interface Web](./003-interface-web.md) — consome os relatorios gerados por este PRD
- [PRD 004 - Agente de Correcao](./004-agente-correcao-automatica.md) — consome os relatorios gerados por este PRD
- [MCP Server Kubernetes (Flux159)](https://github.com/Flux159/mcp-server-kubernetes) — servidor MCP utilizado pelo agente
- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents) — guia de agents (`create_agent`)
- [Referencia da API `create_agent`](https://reference.langchain.com/python/langchain/agents/factory/create_agent) — assinatura e parametros
- [Middleware built-in do LangChain](https://docs.langchain.com/oss/python/langchain/middleware/built-in) — `ModelCallLimitMiddleware` usado no limite de iteracoes
- [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) — pacote de integracao LangChain + MCP

## 9. Registro de Decisoes

Decisoes tomadas em 2026-07-22, apos revisao de design e verificacao das APIs (LangChain OSS v1 + `langchain-mcp-adapters`).

### D1 — Saida do agente: markdown puro

- **Decisao**: o agente responde APENAS com o relatorio em markdown; o mapeamento uid->problema e extraido por parse do campo **Eventos**.
- **Alternativa considerada**: saida hibrida com `ProviderStrategy` (campos tipados `event_uids`/`severidade`/`namespace` + narrativa markdown), que na v1 e integrada ao loop principal sem chamada extra de LLM.
- **Justificativa**: simplicidade na v1. O risco de vazamento do mapeamento (LLM omitir/reformatar um uid) esta registrado na tabela de riscos (§7) e aceito; mitigacao futura e migrar os campos de mapeamento para saida estruturada.

### D2 — Modelo default: Haiku

- **Decisao**: `AGENT_MODEL_NAME` tem default `claude-haiku-4-5`; modelos classe Sonnet ficam como override opcional.
- **Justificativa**: prioriza custo/velocidade na v1. A taxa de acerto de causa raiz sera monitorada (risco #1, §7); se ficar abaixo da meta, promover o default para um modelo de maior capacidade e a primeira alavanca.
- **Ajuste no doc**: removidas as mencoes que fixavam "Claude Sonnet" como o modelo (decisao 2, US02, Milestone 2).

### D3 — Swap de relatorio status-aware

- **Decisao**: a substituicao do relatorio EM_ANALISE do batch pelos relatorios por problema so ocorre se o relatorio ainda estiver EM_ANALISE. Se ja tiver sido transicionado para INCOMPLETO (timeout de estagnacao ou recuperacao de startup durante a analise), o swap e abortado e o resultado do agente e descartado.
- **Justificativa**: evita a race entre uma analise lenta-mas-viva e a recuperacao por `ANALYSIS_STALE_TIMEOUT_MINUTES`, que poderia reintroduzir relatorios para eventos ja liberados para reanalise (analise duplicada). Requer que o `ANALYSIS_STALE_TIMEOUT_MINUTES` seja mantido acima do pior caso de runtime do agente.

### D4 — Semantica da query de deduplicacao

- **Decisao**: a dedup avalia a EXISTENCIA de qualquer relatorio ativo contendo o uid (overlap `event_uids && :uids` com status ativo), nunca o status do relatorio mais recente.
- **Justificativa**: um mesmo uid pode aparecer em varios relatorios ao longo do tempo (ex.: CORRIGIDO antigo + EM_ANALISE atual); avaliar apenas o mais recente poderia liberar indevidamente um evento ja em tratamento.

Decisoes D5–D14 tomadas em 2026-10-18, apos cruzar este PRD com o comportamento real do coletor (PRD 001) e com os PRDs 003/004.

### D5 — Reincidencia de CORRIGIDO por predicado temporal

- **Decisao**: um uid vinculado a relatorio CORRIGIDO so e reanalisado se o `timestamp` do evento for posterior ao `corrected_at` do relatorio.
- **Alternativa considerada**: reanalisar sempre que o status for CORRIGIDO (regra anterior).
- **Justificativa**: o coletor entrega eventos com recencia >= marca d'agua - intervalo (sobreposicao) e, na primeira coleta apos restart, todos os Warnings vivos (~1h de TTL). O mesmo evento antigo voltaria logo apos a correcao e geraria um relatorio novo (provavelmente "recurso saudavel", com botao de correcao) para um problema ja resolvido. `corrected_at` dedicado em vez de `updated_at`, que muda por outros motivos.

### D6 — Cooldown para reanalise de INCOMPLETO

- **Decisao**: uid vinculado a INCOMPLETO so e reanalisado apos `ANALYSIS_RETRY_COOLDOWN_MINUTES` (padrao 30) desde o `created_at` do relatorio (inicio da analise). `updated_at` foi descartado como referencia porque a recuperacao de startup e o timeout de estagnacao o atualizam, o que travaria o evento recuperado por mais um cooldown; com `created_at`, um crash-loop da aplicacao tambem nao dispara uma analise a cada restart.
- **Justificativa**: eventos com `series` ativa (ex.: CrashLoopBackOff) sao reentregues a cada ciclo; sem cooldown, um incidente que o agente nao conclui dispara ate `AGENT_MAX_ITERATIONS` chamadas ao modelo a cada ~3 min, indefinidamente.

### D7 — Substituicao do relatorio do batch por UPDATE + INSERT

- **Decisao**: o relatorio EM_ANALISE do batch e atualizado para virar o Problema 1; os Problemas 2..N sao inseridos.
- **Alternativa considerada**: DELETE do relatorio do batch + INSERT de todos os problemas.
- **Justificativa**: preserva o ID (o detalhe aberto na interface do PRD 003 nao vira 404) e o proprio UPDATE condicional (`WHERE status='EM_ANALISE' RETURNING id`) implementa a substituicao status-aware da D3 de forma atomica — mesmo padrao do PRD 004.

### D8 — Metadados do problema como colunas

- **Decisao**: `severity`, `namespace` e `title` sao gravados em colunas no momento do parse da resposta.
- **Alternativa considerada**: o PRD 003 extrair a severidade por regex do Markdown na renderizacao.
- **Justificativa**: o parse ja acontece aqui (mapeamento de event_uids); um unico ponto de parse desacopla a interface do formato textual. Relatorios sem problema (EM_ANALISE, INCOMPLETO de batch) ficam com NULL.

### D9 — Markdown por problema contem apenas a secao do problema

- **Decisao**: cada relatorio persiste so a secao `## Problema N`, com o titulo promovido para `# <causa>`; a tabela de Resumo nao e persistida.
- **Justificativa**: o Resumo descreve o batch, que deixa de existir apos o split; manter "Problema 2" ou um resumo de varios problemas num relatorio de um problema so confunde o leitor e o agente de correcao (PRD 004).

### D10 — Conclusao explicita e validacao de uids

- **Decisao**: o formato da resposta ganha o campo `**Conclusao:** conclusiva | inconclusiva`, que define COMPLETO/INCOMPLETO por problema; uids citados sao cruzados com o batch (estranhos descartados, duplicados ficam no primeiro problema).
- **Alternativa considerada**: detectar "inconclusiva" no texto livre da Causa Raiz.
- **Justificativa**: o PRD nao definia como decidir INCOMPLETO por problema; um campo deterministico no mesmo parse da D8 e mais robusto que regex sobre prosa.

### D11 — Colunas do PRD 004 na migration inicial

- **Decisao**: `corrected_at` e `correction_result` entram na migration inicial da tabela, nulas ate o PRD 004 preenche-las.
- **Justificativa**: ainda nao ha Alembic; a primeira migration nasce aqui, e duas colunas nulas agora custam menos que uma segunda migration logo em seguida. `corrected_at` e tambem consumida pela D5.

### D12 — Recuperacao de startup antes da primeira coleta

- **Decisao**: a recuperacao EM_ANALISE → INCOMPLETO e aguardada no `lifespan` antes de `collector.start()`.
- **Justificativa**: a primeira coleta nao tem filtro temporal; rodando antes da recuperacao, a dedup trataria orfaos como ativos e ignoraria eventos que deveriam ser liberados.

### D13 — Sessionmaker unico

- **Decisao**: um unico `async_sessionmaker` em `app.state.sessionmaker`, injetado no `EventHandler`; o engine de modulo de `database.py` e removido.
- **Justificativa**: hoje existem dois engines (modulo e `lifespan`); o PRD 004 ja adota `app.state.sessionmaker` como padrao.

### D14 — Sequencia de entrega

- **Decisao**: Milestone 1 deste PRD → (PRD 003 em paralelo ao Milestone 2) → PRD 004.
- **Justificativa**: o PRD 003 depende do modelo de dados, nao do agente; entrega-lo cedo (com relatorios seed) da visibilidade e obriga a fechar o schema antes do agente.

### D15 — Exemplo de comando sugerido com strategic merge patch

- **Decisao**: o exemplo de `### Comando Sugerido` no prompt usa `--type=strategic` em vez de `--type=merge`.
- **Justificativa**: o agente de correcao (PRD 004) proibe merge patch simples sobre a lista `containers`, que substitui o container inteiro e apaga env, image e probes. Com o exemplo em `merge`, o agente de analise era induzido a sugerir justamente o anti-padrao. Pendente no codigo: `src/my_agent_app/agents/prompt.py` ainda usa `--type=merge`.
