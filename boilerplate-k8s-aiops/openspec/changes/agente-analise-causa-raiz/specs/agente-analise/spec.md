## ADDED Requirements

### Requirement: Configuração do agente
O sistema SHALL construir o agente de análise com `create_agent` (`langchain.agents`) e um `ChatAnthropic` cujo modelo vem de `AGENT_MODEL_NAME` (padrão `claude-haiku-4-5`) e cujo `max_retries` é 3. O agente MUST ter `ModelCallLimitMiddleware(run_limit=AGENT_MAX_ITERATIONS, exit_behavior="end")`, com `AGENT_MAX_ITERATIONS` de padrão 25. Valores de `AGENT_MAX_ITERATIONS` não inteiros, zero ou negativos MUST resultar no padrão com warning no log.

#### Scenario: Modelo configurado
- **WHEN** `AGENT_MODEL_NAME` vale `claude-sonnet-4-5`
- **THEN** o agente usa esse modelo

#### Scenario: Limite de iterações inválido
- **WHEN** `AGENT_MAX_ITERATIONS` vale `0`
- **THEN** o limite usado é 25 e um warning é registrado

### Requirement: Tools somente leitura via MCP
O agente SHALL obter as tools do MCP Server Kubernetes com `MultiServerMCPClient` (`transport: "http"`, URL de `MCP_SERVER_URL`, padrão `http://localhost:3001/mcp`, `handle_tool_errors=True`) e MUST vincular apenas `kubectl_get`, `kubectl_describe` e `kubectl_logs`. Qualquer outra tool retornada pelo servidor MUST ser descartada antes da criação do agente.

#### Scenario: Tools de escrita são filtradas
- **WHEN** o MCP Server expõe `kubectl_get`, `kubectl_describe`, `kubectl_logs`, `kubectl_apply` e `kubectl_delete`
- **THEN** o agente é criado apenas com `kubectl_get`, `kubectl_describe` e `kubectl_logs`

#### Scenario: Erro de execução de tool volta ao modelo
- **WHEN** uma chamada de tool falha por parâmetro inválido ou recurso inexistente
- **THEN** o erro chega ao modelo como resultado da tool e a análise continua

### Requirement: Prompt de análise
O agente SHALL receber o prompt definido no PRD 002 (US02), com os eventos liberados do lote serializados em JSON no lugar de `{events}`, mantendo todos os campos do contrato de saída. O formato de resposta MUST incluir, em cada problema, os campos `**Severidade:**`, `**Namespace:**`, `**Recursos Afetados:**`, `**Eventos:**` e `**Conclusao:**`.

#### Scenario: Eventos no prompt
- **WHEN** a análise de um lote com dois eventos é iniciada
- **THEN** a mensagem enviada ao modelo contém o `uid`, o `reason` e o `message` de ambos os eventos

### Requirement: Parse da resposta em problemas
O sistema SHALL dividir a resposta final do agente em uma seção por cabeçalho `## Problema N: <causa>` e extrair de cada seção:
- `title`: a causa após os dois-pontos;
- `severity`: CRITICO, ALTO, MEDIO ou BAIXO; ausente ou desconhecida → nulo, com warning;
- `namespace`;
- `event_uids`: lista do campo **Eventos**;
- status: `conclusiva` → COMPLETO; `inconclusiva` → INCOMPLETO; ausente ou desconhecida → COMPLETO, com warning.

O Markdown persistido de cada problema MUST ser só a sua seção, com o cabeçalho promovido para `# <causa>`. Uids que não pertencem ao lote MUST ser descartados com warning; um uid citado em mais de um problema MUST ficar só no primeiro, com warning; uids do lote não citados em nenhum problema MUST gerar warning.

#### Scenario: Dois problemas independentes
- **WHEN** a resposta contém `## Problema 1` com severidade CRITICO e conclusão conclusiva e `## Problema 2` com severidade ALTO e conclusão inconclusiva
- **THEN** o parse produz dois problemas, o primeiro COMPLETO/CRITICO e o segundo INCOMPLETO/ALTO, cada um com seus uids

#### Scenario: Cabeçalho promovido e Resumo descartado
- **WHEN** a resposta contém a tabela de Resumo e um `## Problema 1: Imagem inexistente`
- **THEN** o Markdown do problema começa com `# Imagem inexistente` e não contém a tabela de Resumo

#### Scenario: Uid estranho e uid duplicado
- **WHEN** um problema cita um uid fora do lote e dois problemas citam o mesmo uid do lote
- **THEN** o uid estranho é descartado, o duplicado fica só no primeiro problema e ambos geram warning

#### Scenario: Resposta sem problemas
- **WHEN** a resposta final é vazia ou não contém nenhum cabeçalho `## Problema`
- **THEN** o parse não produz problemas

### Requirement: Troca do relatório do lote pelos relatórios por problema
Ao concluir a análise com ao menos um problema, o sistema SHALL, numa única transação, atualizar o relatório do lote com os dados do Problema 1 por `UPDATE ... WHERE id = :id AND status = 'EM_ANALISE'` e inserir os Problemas 2..N como novos relatórios. Se o `UPDATE` não afetar nenhuma linha, a transação MUST ser desfeita, nenhum relatório MUST ser inserido e o resultado MUST ser descartado com warning. Sem problemas no parse, o relatório do lote MUST passar a INCOMPLETO (condicional a EM_ANALISE). Falhas do banco nessa gravação MUST ser repetidas até 3 vezes com backoff exponencial; esgotadas as tentativas, o erro MUST ser registrado no log junto com a resposta do agente.

#### Scenario: ID do lote preservado
- **WHEN** a análise de um lote termina com dois problemas
- **THEN** o relatório do lote passa a conter o Problema 1, com o mesmo id, e existe um novo relatório com o Problema 2

#### Scenario: Lote recuperado durante a análise
- **WHEN** a análise termina depois que o relatório do lote foi movido para INCOMPLETO por estagnação
- **THEN** nenhum relatório é alterado ou inserido

#### Scenario: Resposta sem problemas
- **WHEN** o parse não produz problemas
- **THEN** o relatório do lote passa a INCOMPLETO com `markdown` nulo

#### Scenario: Banco indisponível na gravação
- **WHEN** o PostgreSQL falha nas três tentativas de gravar o resultado
- **THEN** o erro e a resposta do agente são registrados no log e o relatório permanece EM_ANALISE até o timeout de estagnação

### Requirement: Falhas de infraestrutura abortam a análise
Falha de conexão com o MCP Server, ou erro da API Anthropic depois das tentativas do SDK, SHALL abortar a análise. O relatório do lote passa então a INCOMPLETO pelo tratamento de falha do handler (capability `relatorios-analise`).

#### Scenario: MCP Server fora do ar
- **WHEN** um lote é analisado e o MCP Server não responde em `MCP_SERVER_URL`
- **THEN** o erro é registrado no log e o relatório do lote passa a INCOMPLETO

#### Scenario: Limite de iterações atingido
- **WHEN** o agente atinge `AGENT_MAX_ITERATIONS` sem escrever o relatório
- **THEN** a execução termina sem nova chamada ao modelo e o relatório do lote passa a INCOMPLETO

### Requirement: Diagnóstico dos cenários de referência
Com o fluxo completo em execução (coletor, deduplicação, agente, MCP Server e PostgreSQL) contra o cluster kind `aiops`, depois de aplicar `manifestos-k8s/nginx.yaml` no namespace `teste-a` e `manifestos-k8s/kube-news.yaml` no namespace `teste-b`, o sistema SHALL produzir relatórios que diagnostiquem as causas raiz desses cenários.

#### Scenario: Imagem inexistente do nginx
- **WHEN** o fluxo completo processa os Warnings do namespace `teste-a`
- **THEN** existe um relatório COMPLETO com `namespace` `teste-a`, severidade preenchida e `event_uids` contendo ao menos um evento do pod `nginx-*`, cujo Markdown identifica a imagem `ngin:latest` como inexistente ou inválida

#### Scenario: Senha divergente do banco do kube-news
- **WHEN** o fluxo completo processa os Warnings do namespace `teste-b`
- **THEN** existe um relatório COMPLETO com `namespace` `teste-b` e `event_uids` contendo ao menos um evento dos pods `kubenews-*`, cujo Markdown identifica falha de autenticação no banco ou divergência de `DB_PASSWORD`

#### Scenario: Todos os eventos de referência têm relatório
- **WHEN** a primeira análise após a aplicação dos manifestos termina
- **THEN** todo uid de evento Warning dos namespaces `teste-a` e `teste-b` entregue ao agente consta do `event_uids` de algum relatório

#### Scenario: Reentrega não gera nova análise
- **WHEN** o coletor roda mais dois ciclos depois da análise
- **THEN** nenhum relatório novo é criado para os eventos já cobertos
