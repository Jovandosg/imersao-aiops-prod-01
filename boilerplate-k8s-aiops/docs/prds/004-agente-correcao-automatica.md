---
prd_number: "004"
status: rascunho
priority: alta
created: 2026-06-16
issue:
depends_on: ["002", "003"]
references: []
---

# PRD 004: Agente de Correção Automática

## 1. Contexto

- **Sistema/produto**: Agente AIOps para Kubernetes — aplicação Python com FastAPI, LangChain e MCP Server Kubernetes. O PRD 002 gera relatórios com causa raiz e passos de correção. O PRD 003 fornece a interface web com botão para acionar a correção. Stack: Python, FastAPI, LangChain, Claude (modelo configurável), MCP Server Kubernetes.
- **Estado atual**: Relatórios de análise são gerados com passos de correção recomendados, mas a execução é manual — o operador precisa ler o relatório, interpretar os passos e executar os comandos no cluster manualmente.
- **Problema**: A correção manual adiciona tempo ao MTTR e está sujeita a erros de execução. Mesmo com um bom diagnóstico automatizado, o benefício é parcial se a correção continua dependendo de intervenção humana.

## 2. Solução Proposta

### Visão geral

- Agente construído com LangChain que, quando acionado, lê o relatório de análise e executa os passos de correção no cluster via MCP Server Kubernetes
- Acionado pelo botão "Executar correção", que este PRD adiciona à página de detalhe do relatório (PRD 003)
- Após executar a correção, o agente verifica se o problema foi resolvido
- Atualiza o status do relatório no banco (CORRIGINDO → CORRIGIDO ou FALHA_CORRECAO)

### Decisões-chave

1. **Agente separado do agente de análise** — Responsabilidades distintas: um investiga, outro corrige. Permite evolução independente (ex: adicionar proteções na correção sem afetar a análise).
2. **Sem mecanismo de proteção na v1** — O agente tem acesso irrestrito ao cluster via MCP. Não haverá whitelist de ações, dry-run ou restrição por namespace. Risco aceito e documentado.
3. **Verificação pós-correção** — O agente verifica se o problema foi resolvido antes de declarar sucesso. Se o problema persiste, marca como falha.

### Fora do escopo

- **Whitelist de ações permitidas** — Não implementado na v1
- **Dry-run ou preview de ações** — Não implementado na v1
- **Restrição por namespace** — Não implementado na v1
- **Aprovação humana antes da execução** — O clique no botão é a aprovação; não há segundo nível de confirmação
- **Rollback automático** — Se a correção piorar o estado, não há mecanismo de reversão automática na v1
- **Proteção contra prompt injection** — O relatório injetado no prompt vem de um LLM alimentado por eventos do cluster; o projeto não trata manipulação desse conteúdo via eventos

## 3. Funcionalidades

### US01: Execução de correção automática

Como SRE, quero poder acionar a correção automática de um problema a partir do relatório, para reduzir o tempo de resolução sem executar comandos manualmente.

**Rules:**
- A página de detalhe do relatório (PRD 003) ganha o botão "Executar correção" (`<form method="post" action="/reports/{id}/fix">`), exibido apenas para relatórios com status COMPLETO ou FALHA_CORRECAO (FALHA_CORRECAO permite nova tentativa após falha de correção)
- O acionamento é feito via endpoint `POST /reports/{id}/fix` na camada web (`web/router.py`, mesma família das rotas `/reports/{id}`)
- O endpoint valida que o relatório existe e tem status COMPLETO ou FALHA_CORRECAO; qualquer outro status é um conflito
- **Conflito no navegador (padrão PRG):** como o acionamento vem de um formulário HTML, o conflito é sinalizado com `303 See Other` para a página de detalhe com um parâmetro que diz o motivo. Semanticamente é um `409 Conflict`; o redirect evita que o browser mostre a resposta crua e que um refresh reenvie o POST (mesmo padrão do 303 de sucesso):
  - status CORRIGINDO → `GET /reports/{id}?erro=em_andamento`; o detalhe exibe "Correção já em andamento"
  - qualquer outro status (EM_ANALISE, INCOMPLETO, CORRIGIDO) → `GET /reports/{id}?erro=status_invalido`; o detalhe exibe "A correção não pode ser iniciada no status atual do relatório" (caso típico: aba antiga de um relatório já CORRIGIDO)
- A transição para CORRIGINDO é feita por UPDATE condicional atômico (`UPDATE reports SET status='CORRIGINDO' WHERE id=:id AND status IN ('COMPLETO','FALHA_CORRECAO') RETURNING id`) — isso evita que duas requisições concorrentes disparem dois agentes de correção para o mesmo relatório (corrida TOCTOU). Se nenhuma linha for atualizada, o endpoint lê o status atual para escolher a resposta: relatório inexistente → 404; CORRIGINDO → `em_andamento`; demais → `status_invalido`. Essa leitura só escolhe a mensagem; a decisão de concorrência já foi tomada pelo UPDATE
- A transição para CORRIGINDO acontece de forma síncrona no request (antes de responder), garantindo que o conflito de concorrência seja decidido antes da resposta; a correção em si roda em background, fora do ciclo do request (sem fila externa): o endpoint a despacha com `asyncio.create_task` para um executor de correção criado no `lifespan` (em `app.state`), que guarda as tasks em execução num conjunto e as cancela no shutdown — mesmo padrão de despacho do coletor de eventos (`EventCollector._handler_tasks`). Não usar `BackgroundTasks` do FastAPI: ele fica preso ao ciclo do request e não oferece cancelamento no shutdown. Semanticamente é um `202 Accepted` (aceito e processado de forma assíncrona), mas — por ser acionado por um `<form method="post">` no browser — o endpoint responde `303 See Other` redirecionando para `GET /reports/{id}`; o usuário vê o badge CORRIGINDO e acompanha a evolução via refresh da página (sem JS/polling no v1). O trabalho roda in-process e é perdido em caso de restart — daí a recuperação de startup descrita abaixo
- A task de correção NÃO reutiliza a sessão do request (que é fechada junto com a resposta 303): ela abre a sua própria `AsyncSession` a partir de `app.state.sessionmaker` e recebe apenas o `report_id` (UUID), nunca o objeto ORM ligado à sessão do request — mesmo padrão do coletor de eventos
- O resultado da correção é consultado pela página de detalhe do relatório (PRD 003), que exibe o status atualizado e o **feedback da correção** (resposta do agente: Ações Executadas + validação) persistido na coluna `correction_result`, numa seção "Resultado da Correção" que este PRD adiciona ao template de detalhe. A coluna `correction_result` já existe desde a migration inicial do PRD 002 (decisão D11 daquele PRD)
- Na transição para CORRIGIDO, a coluna `corrected_at` é preenchida com o instante da transição; o PRD 002 usa esse valor para distinguir reincidência real de reentrega do mesmo evento antigo pelo coletor (decisão D5 daquele PRD). Transições para FALHA_CORRECAO não alteram `corrected_at`
- O agente é construído com LangChain e se conecta ao cluster via MCP Server Kubernetes (Flux159), usando `langchain-mcp-adapters` para conectar por HTTP (`streamable_http`) ao MCP executado localmente via `npx` (transport HTTP/streamable) em `MCP_SERVER_URL` (padrão `http://localhost:3001/mcp`) — mesmo padrão do PRD 002
- O modelo é configurável via variável de ambiente `CORRECTION_MODEL_NAME`; se ausente ou vazia, usa o valor de `AGENT_MODEL_NAME` do PRD 002 (padrão: `claude-haiku-4-5`). Permite um modelo mais forte para a correção, que tem escrita irrestrita no cluster, sem encarecer a análise
- Ao contrário do agente de análise, todas as tools do MCP Server são expostas ao agente de correção (acesso irrestrito, conforme decisão-chave 2)
- O número máximo de iterações é configurável via `CORRECTION_MAX_ITERATIONS` (padrão: 25), implementado com `ModelCallLimitMiddleware(run_limit, exit_behavior="end")`; ao atingir o limite o run termina graciosamente (sem nova chamada ao modelo) e a resposta final não segue o formato `CORRIGIDO:/FALHA:`, de modo que o parsing do veredito (ver abaixo) a classifica como FALHA_CORRECAO — não há detecção separada de "limite atingido"
- O relatório de análise inteiro (conteúdo Markdown) é injetado no prompt do agente (`{report_markdown}`); ele interpreta as subseções `### Solucao Recomendada` e `### Comando Sugerido` produzidas pelo PRD 002 (dentro do bloco do problema; no relatório persistido, o título do problema vira o `# <titulo>` do Markdown) e traduz o comando sugerido em chamadas de tool MCP estruturadas (ex: `kubectl_patch`, `kubectl_scale`)
- O agente executa os passos de correção no cluster via MCP
- Na v1, o agente tem acesso irrestrito ao cluster
- Relatórios órfãos em CORRIGINDO encontrados no startup da aplicação são marcados como FALHA_CORRECAO (recuperação de correções interrompidas por crash/restart); como FALHA_CORRECAO é um status re-acionável, a correção pode ser disparada novamente
- **Invariante: um relatório só sai de CORRIGINDO depois que o agente parou de fato.** Trocar o rótulo com o agente ainda vivo reexibiria o botão e permitiria um segundo agente no mesmo recurso; ao contrário da análise (PRD 002), as ações já aplicadas no cluster não podem ser descartadas
- A transição para CORRIGINDO grava `correction_started_at` com o instante da transição (nova coluna, via migration); é a referência de tempo para timeout e estagnação (`created_at` é o nascimento do relatório e pode ter dias)
- **Timeout da correção:** a execução do agente roda sob `asyncio.timeout(CORRECTION_TIMEOUT_MINUTES)` (padrão: 10, aceita fração; inválido cai no padrão). Ao estourar, o task é cancelado e o relatório vai para FALHA_CORRECAO. O limite de iterações não substitui o timeout: ele limita chamadas ao modelo, não o tempo de uma tool pendurada no MCP
- **Falha não prevista:** qualquer exceção na execução da correção é capturada e leva o relatório a FALHA_CORRECAO, além dos casos específicos (MCP indisponível, API do Claude) listados nos edge cases
- **Gravação final condicional:** a transição de saída (CORRIGIDO ou FALHA_CORRECAO) é `UPDATE ... WHERE id=:id AND status='CORRIGINDO'`, com retry com backoff em erro transitório de banco (mesmo padrão de persistência do analisador do PRD 002); um escritor atrasado nunca sobrescreve um estado posterior
- **Varredura de estagnação:** relatórios em CORRIGINDO com `correction_started_at` anterior a `agora − 2 × CORRECTION_TIMEOUT_MINUTES` são marcados FALHA_CORRECAO. Roda a cada ciclo do coletor, na mesma transação da varredura de estagnação do PRD 002. O limite é derivado do timeout (sem env var própria), garantindo que a varredura nunca alcance um agente ainda vivo; ela cobre só o caso em que o agente terminou mas a gravação final falhou
- **`correction_result` em toda saída de CORRIGINDO:** é limpo na transição para CORRIGINDO (uma nova tentativa não exibe o resultado da anterior) e sempre preenchido na saída — resposta do agente no caso normal; nos demais, mensagem fixa por causa:
  - timeout: "Tempo limite atingido após N min; ações parciais podem ter sido aplicadas no cluster — verifique antes de tentar novamente"
  - exceção: "Correção interrompida por erro: <mensagem>; ações parciais podem ter sido aplicadas no cluster"
  - órfão no startup ou varredura: "Correção interrompida (reinício da aplicação ou estagnação); ações parciais podem ter sido aplicadas no cluster"

**Prompt do agente:**

```
Voce e um agente AIOps especializado em correcao de problemas em clusters Kubernetes.
Voce opera no padrao ReAct: para cada acao, primeiro raciocine, depois execute, depois observe o resultado.

Abaixo esta o relatorio de diagnostico com as correcoes recomendadas:

{report_markdown}

## REGRAS
- Execute as correcoes descritas no relatorio. NAO corrija problemas pre-existentes sem relacao com o relatorio (esses sim estao fora de escopo).
- POREM, se a SUA propria correcao introduzir um novo erro ou deixar o recurso pior, isso NAO esta fora de escopo: foi voce que causou e voce DEVE corrigir ate o recurso ficar saudavel.
- Ao editar um container existente (image, env, resources, probes) com kubectl_patch, use patchType "strategic" OU kubectl_apply. NUNCA use merge patch simples sobre a lista `containers`: o merge substitui o container inteiro e APAGA os campos nao citados (env, image, probes, ports).
- NUNCA delete namespaces, PersistentVolumeClaims ou recursos em kube-system.
- NUNCA escale deployments para 0 replicas (a menos que o relatorio peca explicitamente).
- Se um recurso nao existir mais, registre e passe ao proximo passo.
- NUNCA repita a mesma chamada de ferramenta com os mesmos parametros: se falhar, leia a mensagem de erro e tente uma abordagem diferente.
- Se o mesmo passo falhar 2 vezes mesmo com abordagens diferentes, registre o erro e siga adiante.

## COMO CORRIGIR (padrao ReAct)
Para CADA passo de correcao do relatorio, siga este ciclo:

### 1. RACIOCINAR
Antes de agir, responda mentalmente:
- Qual e o estado atual esperado do recurso?
- Qual acao vou executar e por que?
- O que pode dar errado?

### 2. VERIFICAR ESTADO ATUAL
Use kubectl_get ou kubectl_describe para confirmar que o problema ainda existe.
- Se o problema ja foi resolvido, registre como "Ja resolvido" e pule para o proximo.

### 3. EXECUTAR A CORRECAO
Use a ferramenta apropriada (kubectl_patch, kubectl_apply, kubectl_scale, kubectl_rollout, etc.).
Ao alterar um container, prefira patchType "strategic" ou kubectl_apply para PRESERVAR os demais campos (env, image, probes, ports). Nunca remova variaveis de ambiente, a imagem ou probes que ja existiam, a menos que o relatorio peca.

### 4. VALIDAR O RESULTADO
Apos executar, use kubectl_get ou kubectl_describe para verificar de fato a SAUDE do recurso afetado:
- O recurso esta no estado esperado?
- O pod esta Running E Ready (sem CrashLoopBackOff, sem restarts subindo, sem novos erros em eventos/logs)?
- A sua correcao NAO introduziu nenhum erro novo?

Se a validacao mostrar que a SUA correcao causou um novo erro ou deixou o pod quebrado (ex.: saiu de ImagePullBackOff mas entrou em CrashLoop porque o patch apagou variaveis de ambiente), NAO trate isso como "fora de escopo": foi a sua acao que causou, entao CORRIJA. Volte ao ciclo (raciocine -> verifique -> execute -> valide) ate o recurso ficar saudavel, respeitando o limite de iteracoes.

So considere o problema CORRIGIDO quando o recurso afetado estiver comprovadamente saudavel (pod Running e Ready, Deployment Available, sem novos erros). Se, depois das suas tentativas, o recurso continuar quebrado, responda FALHA explicando o que ficou pendente.

## FORMATO DE RESPOSTA
IMPORTANTE: A PRIMEIRA LINHA da sua resposta DEVE ser exatamente uma destas (sem markdown, sem emoji, sem formatacao):
- CORRIGIDO: [resumo de uma linha]
- FALHA: [resumo de uma linha]

Depois da primeira linha, use o formato abaixo:

## Acoes Executadas

### Problema 1: [titulo do problema do relatorio]
- **Status:** Corrigido | Falha | Ja resolvido | Recurso nao encontrado
- **Acao:** o que foi feito
- **Validacao:** resultado da verificacao pos-correcao

### Problema 2: ...

## Resumo
- Corrigidos: X
- Falhas: X
- Ja resolvidos: X
- Total: X
```

> Nota: como cada relatório corresponde a um único problema (decisão do PRD 002), na prática a resposta terá apenas "Problema 1"; o formato suporta múltiplos problemas por robustez.

**Parsing da resposta:** O **veredito** da resposta do agente determina o status do relatório no banco: uma linha que comece com `CORRIGIDO:` → status `CORRIGIDO`; com `FALHA:` → status `FALHA_CORRECAO`. O parser localiza o veredito em **qualquer linha** da resposta (não apenas a primeira), pois o agente costuma escrever um resumo em prosa antes do veredito; o token deve ancorar no início de uma linha (tolerando marcação Markdown como `-`, `*`, `#`, `>`) para não casar com menções no meio de frase. Regra conservadora quando houver mais de uma linha de veredito: **qualquer `FALHA:` → `FALHA_CORRECAO`**; `CORRIGIDO` só quando todas as linhas de veredito forem `CORRIGIDO:`. Se nenhum veredito for encontrado, tratar como `FALHA_CORRECAO` e registrar warning no log.

**Edge cases:**
- Passos de correção referenciam recursos que não existem mais → agente registra que o recurso não foi encontrado e continua com os próximos passos
- MCP Server indisponível durante a correção → abortar e atualizar status para FALHA_CORRECAO
- Erro na API do Claude durante a correção → `max_retries=3` no `ChatAnthropic` aplica backoff exponencial automaticamente (mesmo mecanismo do PRD 002); após 3 tentativas, abortar e atualizar status para FALHA_CORRECAO
- Agente de correção já em execução para o mesmo relatório → conflito (status CORRIGINDO): `303` para `/reports/{id}?erro=em_andamento`, detalhe exibe "Correção já em andamento" (proteção server-side via UPDATE condicional atômico)
- Relatório em EM_ANALISE, INCOMPLETO ou CORRIGIDO → conflito: `303` para `/reports/{id}?erro=status_invalido`, detalhe exibe "A correção não pode ser iniciada no status atual do relatório"
- Aplicação encerrada (shutdown) durante a correção → o executor cancela as tasks em andamento; o relatório fica em CORRIGINDO e é marcado FALHA_CORRECAO pela recuperação no próximo startup
- Aplicação reinicia durante a correção → relatório órfão em CORRIGINDO é marcado como FALHA_CORRECAO no startup, permitindo nova tentativa pelo botão "Executar correção" da página de detalhe
- Relatório não encontrado → endpoint retorna `404 Not Found`
- MCP ou tool pendurada sem erro nem resposta → timeout cancela o agente; FALHA_CORRECAO com a mensagem de tempo limite
- Banco indisponível na gravação final, mesmo após o retry → relatório fica em CORRIGINDO com o agente já parado; a varredura de estagnação o marca FALHA_CORRECAO

### US02: Verificação pós-correção

Como SRE, quero que o agente verifique se o problema foi resolvido após a correção, para ter confiança no resultado sem precisar verificar manualmente.

**Rules:**
- Após executar os passos de correção, o agente verifica o estado dos recursos no cluster via MCP
- O status só é CORRIGIDO se o recurso afetado ficar comprovadamente saudável (pod Running e Ready, Deployment Available, sem novos erros); caso contrário, FALHA_CORRECAO
- Se a própria correção introduzir um novo erro (ex.: um patch destrutivo que apaga variáveis de ambiente), o agente deve corrigi-lo — e não tratá-lo como "problema separado fora de escopo"
- Se o problema persiste, o status é atualizado para FALHA_CORRECAO

**Edge cases:**
- Verificação indica estado ambíguo (parcialmente corrigido) → já resolvido pelo mecanismo de parsing: qualquer problema com falha faz o agente responder `FALHA:` → status `FALHA_CORRECAO`; o corpo da resposta (seção "Ações Executadas") detalha o que foi corrigido e o que falhou
- Recurso demora para estabilizar após correção (ex: pod reiniciando) → limitação conhecida na v1: o agente verifica o estado imediatamente após cada ação, sem aguardar estabilização; pods em inicialização podem gerar falso FALHA_CORRECAO

## 4. Visão de Arquitetura

```
┌───────────────────────────────────────────────────────┐
│                Pipeline de Correção                    │
│                                                        │
│  Interface Web (PRD 003)                               │
│  [Botão "Executar correção"]                           │
│       │                                                │
│       ▼                                                │
│  ┌──────────────────────┐                              │
│  │ POST /reports/{id}/  │                              │
│  │ fix                  │──▶ 303 See Other (→ detalhe) │
│  │ (validação + dispatch│                              │
│  │  assíncrono)         │                              │
│  └────────┬─────────────┘                              │
│           │ background task                            │
│           ▼                                            │
│  ┌──────────────────────┐                              │
│  │  Agente de Correção  │                              │
│  │ (LangChain + Claude) │                              │
│  └────────┬─────────────┘                              │
│           │                                            │
│     ┌─────┴──────┐                                     │
│     │            │                                     │
│     ▼            ▼                                     │
│  ┌──────────┐  ┌──────────────┐                        │
│  │ Leitura  │  │ Execução     │                        │
│  │ Relatório│  │ via MCP      │──▶ Cluster K8s         │
│  │ (PG)     │  │ (Flux159)    │                        │
│  └──────────┘  └──────┬───────┘                        │
│                       │                                │
│                       ▼                                │
│              ┌─────────────────┐                       │
│              │ Verificação     │                       │
│              │ pós-correção    │──▶ Cluster K8s         │
│              │ (via MCP)       │                       │
│              └────────┬────────┘                       │
│                       │                                │
│              ┌────────┴────────┐                       │
│              │                 │                       │
│              ▼                 ▼                       │
│  ┌────────────────┐  ┌─────────────────┐               │
│  │ Status:        │  │ Status:         │               │
│  │ CORRIGIDO      │  │ FALHA_CORRECAO  │               │
│  └────────────────┘  └─────────────────┘               │
└───────────────────────────────────────────────────────┘
```

## 5. Critérios de Aceite

### Técnicos

| Critério | Método de verificação |
|----------|----------------------|
| Agente lê relatório e executa passos de correção via MCP | Teste de integração com cenário de erro conhecido e correção previsível |
| Status do relatório atualizado corretamente (CORRIGINDO → CORRIGIDO ou FALHA_CORRECAO) | Teste automatizado verificando transições de status |
| Verificação pós-correção detecta se problema persiste | Teste com cenário onde correção não resolve o problema |
| Endpoint `POST /reports/{id}/fix` responde 303 (redirect para o detalhe) e processa a correção em background | Teste de integração validando o redirect e a execução assíncrona |
| Endpoint sinaliza conflito (303) para status diferente de COMPLETO/FALHA_CORRECAO: `em_andamento` para CORRIGINDO, `status_invalido` para os demais | Teste com relatórios em status CORRIGINDO, EM_ANALISE, INCOMPLETO, CORRIGIDO |
| Detalhe exibe a mensagem de cada parâmetro (`em_andamento`, `status_invalido`) | Teste automatizado da rota de detalhe com cada parâmetro |
| Veredito com `FALHA:` e `CORRIGIDO:` na mesma resposta resulta em FALHA_CORRECAO | Teste unitário do parser do veredito |
| Shutdown cancela correções em andamento | Teste do executor: task pendente é cancelada no `stop()` |
| Botão "Executar correção" aparece apenas para COMPLETO ou FALHA_CORRECAO | Teste automatizado renderizando o detalhe em cada status |
| `corrected_at` é preenchido na transição para CORRIGIDO | Teste automatizado verificando a coluna após veredito `CORRIGIDO:` |
| Endpoint aceita FALHA_CORRECAO e reinicia a correção | Teste acionando `/fix` em relatório FALHA_CORRECAO e validando transição para CORRIGINDO |
| Transição COMPLETO/FALHA_CORRECAO → CORRIGINDO é atômica (rejeita concorrência) | Teste de concorrência: duas requisições simultâneas, apenas uma dispara a correção |
| Relatório CORRIGINDO órfão é marcado FALHA_CORRECAO no startup | Teste simulando restart com relatório em CORRIGINDO |
| Endpoint retorna 404 para relatório inexistente | Teste com ID inválido |
| Correção que excede `CORRECTION_TIMEOUT_MINUTES` é cancelada e vira FALHA_CORRECAO | Teste com agente fake que não termina e timeout curto |
| Varredura marca FALHA_CORRECAO só após 2× o timeout | Teste com `correction_started_at` antes e depois do limite |
| Gravação final não sobrescreve relatório que já saiu de CORRIGINDO | Teste gravando veredito em relatório já FALHA_CORRECAO |
| `correction_result` é limpo ao entrar em CORRIGINDO e preenchido em toda saída | Teste de nova tentativa a partir de FALHA_CORRECAO e dos caminhos de timeout/exceção |

### De negócio

| Métrica | Baseline (fonte) | Meta | Prazo | Mín. aceitável | Responsável |
|---------|-------------------|------|-------|-----------------|-------------|
| Taxa de correção automática bem-sucedida | N/A — correção é 100% manual hoje | > 50% | 30 dias após deploy | > 30% | Time de SRE |
| Tempo médio de correção (do acionamento ao resultado) | 15-60min manual (estimativa do time de SRE) | < 5 minutos | 30 dias após deploy | < 15 minutos | Time de SRE |

## 6. Milestones

### Milestone 1: Implementar Agente de Correção

**Objetivo:** Agente executa passos de correção do relatório e verifica resultado.

**Funcionalidades:** US01, US02

- [ ] Adicionar à página de detalhe (PRD 003) o botão "Executar correção" (COMPLETO/FALHA_CORRECAO), as mensagens para `?erro=em_andamento` e `?erro=status_invalido` e a seção "Resultado da Correção" (US01)
- [ ] Implementar endpoint `POST /reports/{id}/fix` aceitando status COMPLETO ou FALHA_CORRECAO, com transição atômica para CORRIGINDO (UPDATE condicional), conflito via 303 + `?erro=em_andamento`/`status_invalido` e dispatch via `asyncio.create_task` para o executor de correção (US01)
- [ ] Criar o executor de correção no `lifespan` (`app.state`), com conjunto de tasks e cancelamento no shutdown, no padrão do `EventCollector` (US01)
- [ ] Configurar agente LangChain com `CORRECTION_MODEL_NAME` (fallback para `AGENT_MODEL_NAME`, padrão `claude-haiku-4-5`) e MCP Server Kubernetes via `langchain-mcp-adapters` (MCP via `npx` com transport HTTP/streamable, conexão `streamable_http` em `MCP_SERVER_URL`), expondo todas as tools do MCP (acesso irrestrito) (US01)
- [ ] Implementar limite de iterações via `CORRECTION_MAX_ITERATIONS` (padrão: 25) com `ModelCallLimitMiddleware(run_limit, exit_behavior="end")`; ao atingir o limite, a classificação FALHA_CORRECAO vem do fallback do parsing do veredito (sem detecção separada) (US01)
- [ ] Implementar leitura do relatório e extração dos passos de correção (US01)
- [ ] Implementar execução dos passos via MCP (US01)
- [ ] Atualizar status do relatório (CORRIGINDO → CORRIGIDO/FALHA_CORRECAO), preenchendo `corrected_at` na transição para CORRIGIDO (US01, US02)
- [ ] Implementar recuperação de startup: marcar relatórios CORRIGINDO órfãos como FALHA_CORRECAO (US01)
- [ ] Criar migration da coluna `correction_started_at` e gravá-la na transição para CORRIGINDO (US01)
- [ ] Implementar timeout via `CORRECTION_TIMEOUT_MINUTES` (padrão: 10), captura de exceção não prevista e gravação final condicional com retry (US01)
- [ ] Implementar varredura de estagnação de CORRIGINDO (2× o timeout) no ciclo do coletor (US01)
- [ ] Limpar `correction_result` ao entrar em CORRIGINDO e preenchê-lo em toda saída, com mensagens fixas para timeout, exceção e interrupção (US01)
- [ ] Implementar verificação pós-correção via MCP (US02)
- [ ] Configurar `max_retries=3` no `ChatAnthropic` para retry com backoff exponencial nativo do SDK (US01)

**Critério de conclusão:**
- Condição: Dado um relatório com passos de correção, o agente executa os passos no cluster e verifica se o problema foi resolvido
- Verificação: Teste de integração end-to-end com cenário de erro conhecido e correção previsível
- Aprovador: Time de SRE

## 7. Riscos e Dependências

| Risco | Impacto | Mitigação | Status |
|-------|---------|-----------|--------|
| Agente com acesso irrestrito pode executar ações destrutivas baseado em análise incorreta ou manipulada (prompt injection via eventos do cluster) | Alto | Aceito na v1; prompt injection fora do escopo do projeto. Versões futuras: whitelist, dry-run, restrição por namespace, aprovação humana | Pendente |
| Correção piora o estado do cluster sem mecanismo de rollback | Alto | Relatório disponível para revisão humana antes de acionar correção. Sem rollback automático na v1; após FALHA_CORRECAO a correção pode ser re-acionada manualmente (mitigação parcial) | Pendente |
| Custo de API do Claude para o agente de correção | Médio | Monitorar uso de tokens. Correção tende a ser mais curta que análise | Pendente |

**Dependências:**

| Dependência | Tipo | Status | Impacto se bloqueado |
|-------------|------|--------|----------------------|
| PRD 002 — Relatórios com passos de correção | Interna | Em desenvolvimento | Sem relatórios, não há o que corrigir |
| PRD 003 — Interface web (página de detalhe onde o botão é adicionado) | Interna | Em desenvolvimento | Sem a página de detalhe, não há onde acionar a correção |
| LangChain (`langchain` + `langchain-anthropic`) | Externa | Disponível | Framework base do agente |
| `langchain-mcp-adapters` | Externa | Disponível — `langchain-mcp-adapters>=0.1.0` em `pyproject.toml` | Bridge entre LangChain e MCP Server Kubernetes |
| MCP Server Kubernetes (Flux159) | Externa | Disponível | Sem MCP, agente não interage com o cluster |
| Node.js + npx (runtime do MCP Server Kubernetes, executado localmente com transport HTTP) | Externa | A provisionar | Sem o runtime Node, o MCP server não inicia |
| API Claude (Anthropic) | Externa | Disponível | Sem LLM, agente não funciona |

## 8. Referências

- [PRD 002 - Agente de Análise](./002-agente-analise-causa-raiz.md) — fornece os relatórios com passos de correção
- [PRD 003 - Interface Web](./003-interface-web.md) — fornece a página de detalhe onde o botão de correção é adicionado
- [MCP Server Kubernetes (Flux159)](https://github.com/Flux159/mcp-server-kubernetes) — servidor MCP utilizado pelo agente

## 9. Registro de Decisões

- **2026-10-18** — **Botão "Executar correção" passa a ser entregue por este PRD** (antes no PRD 003), junto com o endpoint e a seção "Resultado da Correção". Motivo: entregue no PRD 003, o botão apontaria para uma rota inexistente até este PRD.
- **2026-10-18** — **Conflito sinalizado por `303 → /reports/{id}?erro=em_andamento`** em vez de um 409 cru. Motivo: o acionamento é um `<form method="post">`; o 409 cru seria exibido como resposta bruta pelo browser. O redirect mantém o padrão PRG do caminho de sucesso e evita reenvio do POST no refresh.
- **2026-10-18** — **`corrected_at` preenchido na transição para CORRIGIDO.** Motivo: o PRD 002 (decisão D5) usa essa coluna para só reanalisar eventos observados após a correção. A coluna e `correction_result` já existem desde a migration inicial do PRD 002 (decisão D11).
- **2026-10-18** — **Saída de CORRIGINDO só com o agente parado; timeout no task + varredura como rede de segurança.** Motivo: copiar a estagnação "só de rótulo" do PRD 002 reabriria a corrida que o UPDATE condicional fecha — o agente antigo seguiria agindo no cluster enquanto um novo era disparado. O timeout (10 min, entre a meta de 5 e o mínimo aceitável de 15) cancela o agente; a varredura usa 2× o timeout, derivado para que não exista configuração em que ela alcance um agente vivo.
- **2026-10-18** — **Coluna `correction_started_at`** em vez de `updated_at` como referência de tempo. Motivo: `updated_at` só funcionaria enquanto nada mais tocasse a linha durante CORRIGINDO — premissa implícita e frágil.
- **2026-10-18** — **`correction_result` limpo na entrada e sempre preenchido na saída de CORRIGINDO.** Motivo: sem isso, a nova tentativa exibiria o resultado da anterior, e as falhas por timeout/exceção/restart deixariam a seção vazia justamente quando o operador precisa saber que ações parciais podem ter sido aplicadas.
- **2026-10-18** — **Despacho via `asyncio.create_task` num executor do `lifespan`, em vez de `BackgroundTasks`.** Motivo: `BackgroundTasks` fica preso ao ciclo do request e não é cancelável no shutdown; o executor segue o padrão já usado pelo coletor (conjunto de tasks + cancelamento no `stop()`), mantendo um único modelo de concorrência no projeto. O timeout da correção roda dentro da task.
- **2026-10-18** — **Conflito distingue `em_andamento` (CORRIGINDO) de `status_invalido` (demais status).** Motivo: o mesmo redirect cobria CORRIGIDO, e "Correção já em andamento" enganava quem voltava a uma aba antiga de um relatório já corrigido.
- **2026-10-18** — **Veredito conservador: qualquer `FALHA:` vence.** Motivo: o parser busca o veredito em qualquer linha, e o PRD não definia o resultado quando aparecem `FALHA:` e `CORRIGIDO:` na mesma resposta; CORRIGIDO só deve existir quando nada indica falha. Também foram removidas as menções a "parsing da primeira linha", que contradiziam a regra.
- **2026-10-18** — **`CORRECTION_MODEL_NAME` com fallback para `AGENT_MODEL_NAME`.** Motivo: o contexto citava "Claude Sonnet" enquanto a regra herdava o haiku da análise; a env var própria permite um modelo mais forte só na correção, sem mudar nada para quem não a configurar.
- **2026-10-18** — **Prompt injection fora do escopo do projeto.** O risco de um relatório manipulado por eventos do cluster levar o agente de correção a executar ações indevidas é aceito, junto com o acesso irrestrito da v1.
