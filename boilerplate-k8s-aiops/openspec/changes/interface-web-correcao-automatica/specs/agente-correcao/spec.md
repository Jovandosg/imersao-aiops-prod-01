## ADDED Requirements

### Requirement: Botão de correção e mensagens no detalhe
A página de detalhe SHALL exibir o botão "Executar correção" (`<form method="post" action="/reports/{id}/fix">`) apenas para relatórios COMPLETO ou FALHA_CORRECAO. Com o parâmetro `?erro=em_andamento`, MUST exibir "Correção já em andamento"; com `?erro=status_invalido`, MUST exibir "A correção não pode ser iniciada no status atual do relatório".

#### Scenario: Botão nos status acionáveis
- **WHEN** o detalhe de um relatório COMPLETO ou FALHA_CORRECAO é renderizado
- **THEN** a página contém o formulário POST para `/reports/{id}/fix`

#### Scenario: Botão ausente nos demais status
- **WHEN** o detalhe de um relatório EM_ANALISE, INCOMPLETO, CORRIGINDO ou CORRIGIDO é renderizado
- **THEN** a página não contém o formulário de correção

#### Scenario: Mensagem de correção em andamento
- **WHEN** o detalhe é acessado com `?erro=em_andamento`
- **THEN** a página exibe "Correção já em andamento"

#### Scenario: Mensagem de status inválido
- **WHEN** o detalhe é acessado com `?erro=status_invalido`
- **THEN** a página exibe "A correção não pode ser iniciada no status atual do relatório"

### Requirement: Seção Resultado da Correção
Quando `correction_result` não for nulo, a página de detalhe SHALL exibir uma seção "Resultado da Correção" com esse conteúdo, convertido de Markdown para HTML pelas mesmas regras do relatório (no servidor, HTML embutido como texto).

#### Scenario: Resultado presente
- **WHEN** o detalhe de um relatório CORRIGIDO com `correction_result` é renderizado
- **THEN** a página exibe a seção "Resultado da Correção" com o conteúdo renderizado

#### Scenario: Resultado ausente
- **WHEN** o detalhe de um relatório COMPLETO com `correction_result` nulo é renderizado
- **THEN** a página não exibe a seção "Resultado da Correção"

### Requirement: Acionamento da correção
`POST /reports/{id}/fix` SHALL tentar a transição para CORRIGINDO com um único `UPDATE` condicional (`WHERE id=:id AND status IN ('COMPLETO','FALHA_CORRECAO')`), que também grava `correction_started_at` com o instante da transição e limpa `correction_result`. A transição MUST ser decidida antes da resposta. Em caso de sucesso, o endpoint MUST despachar a correção e responder `303` para `GET /reports/{id}`. Se nenhuma linha for atualizada, o endpoint MUST ler o status atual apenas para escolher a resposta:
- relatório inexistente → 404;
- CORRIGINDO → `303` para `/reports/{id}?erro=em_andamento`;
- qualquer outro status → `303` para `/reports/{id}?erro=status_invalido`.

#### Scenario: Acionamento de relatório completo
- **WHEN** `POST /reports/{id}/fix` é enviado para um relatório COMPLETO
- **THEN** o relatório passa a CORRIGINDO com `correction_started_at` preenchido, a correção é despachada e a resposta é `303` para `/reports/{id}`

#### Scenario: Nova tentativa após falha
- **WHEN** `POST /reports/{id}/fix` é enviado para um relatório FALHA_CORRECAO com `correction_result` de uma tentativa anterior
- **THEN** o relatório passa a CORRIGINDO com `correction_result` nulo

#### Scenario: Correção já em andamento
- **WHEN** `POST /reports/{id}/fix` é enviado para um relatório CORRIGINDO
- **THEN** a resposta é `303` para `/reports/{id}?erro=em_andamento` e nenhuma correção é despachada

#### Scenario: Status não acionável
- **WHEN** `POST /reports/{id}/fix` é enviado para um relatório EM_ANALISE, INCOMPLETO ou CORRIGIDO
- **THEN** a resposta é `303` para `/reports/{id}?erro=status_invalido` e o status não muda

#### Scenario: Relatório inexistente
- **WHEN** `POST /reports/{id}/fix` é enviado com um UUID que não existe
- **THEN** a resposta é 404

#### Scenario: Requisições concorrentes
- **WHEN** duas requisições `POST /reports/{id}/fix` chegam ao mesmo tempo para um relatório COMPLETO
- **THEN** apenas uma despacha a correção e a outra recebe `303` com `?erro=em_andamento`

### Requirement: Execução da correção fora do request
A correção SHALL rodar numa task `asyncio` despachada para um executor criado no `lifespan` e guardado em `app.state`, nunca em `BackgroundTasks`. A task MUST receber apenas o `report_id` e abrir a própria `AsyncSession` a partir de `app.state.sessionmaker`. O executor MUST guardar as tasks em execução e cancelá-las no shutdown.

#### Scenario: Resposta não espera a correção
- **WHEN** `POST /reports/{id}/fix` despacha uma correção que leva minutos
- **THEN** a resposta `303` é enviada sem esperar a correção terminar

#### Scenario: Shutdown cancela correções
- **WHEN** a aplicação é encerrada com uma correção em execução
- **THEN** a task é cancelada e o relatório permanece CORRIGINDO até a recuperação do próximo startup

### Requirement: Configuração do agente de correção
O agente SHALL usar `ChatAnthropic` com `max_retries=3` e o modelo de `CORRECTION_MODEL_NAME`; se ausente ou vazia, o valor de `AGENT_MODEL_NAME` (padrão `claude-haiku-4-5`). O número de chamadas ao modelo MUST ser limitado por `ModelCallLimitMiddleware(run_limit=CORRECTION_MAX_ITERATIONS, exit_behavior="end")`, com `CORRECTION_MAX_ITERATIONS` inteiro positivo (padrão 25). `CORRECTION_TIMEOUT_MINUTES` MUST aceitar fração (padrão 10). Valores inválidos, zero ou negativos MUST cair no padrão com warning no log.

#### Scenario: Modelo próprio da correção
- **WHEN** `CORRECTION_MODEL_NAME` está definida
- **THEN** o agente de correção usa esse modelo, independentemente de `AGENT_MODEL_NAME`

#### Scenario: Fallback para o modelo da análise
- **WHEN** `CORRECTION_MODEL_NAME` está ausente e `AGENT_MODEL_NAME` está definida
- **THEN** o agente de correção usa o valor de `AGENT_MODEL_NAME`

#### Scenario: Valor inválido
- **WHEN** `CORRECTION_MAX_ITERATIONS` ou `CORRECTION_TIMEOUT_MINUTES` é inválido, zero ou negativo
- **THEN** o padrão é usado e um warning é registrado

### Requirement: Acesso irrestrito ao cluster via MCP
O agente de correção SHALL receber todas as tools expostas pelo MCP Server Kubernetes, conectando por HTTP (`langchain-mcp-adapters`) em `MCP_SERVER_URL`, sem filtro de tools. Cliente MCP e agente MUST ser criados a cada correção. Erros de execução de uma tool MUST ser devolvidos ao agente como resultado de erro, e não interromper a correção; falhas de conexão com o MCP Server continuam levando a FALHA_CORRECAO.

#### Scenario: Tools de escrita disponíveis
- **WHEN** o MCP Server expõe `kubectl_get`, `kubectl_patch` e `kubectl_scale`
- **THEN** as três tools são entregues ao agente de correção

#### Scenario: Erro de execução de tool volta para o agente
- **WHEN** uma tool chamada pelo agente falha no MCP Server com erro JSON-RPC (ex.: `kubectl rollout status` estoura o timeout)
- **THEN** o erro é entregue ao agente como resultado de erro da tool e a correção continua, sem ir para FALHA_CORRECAO por causa dessa chamada

### Requirement: Prompt de correção
O prompt SHALL ser o do PRD 004, com o Markdown completo do relatório injetado em `{report_markdown}`, incluindo as regras de não deletar namespaces, PVCs ou recursos em `kube-system`, de não usar merge patch simples sobre `containers` e de corrigir erros introduzidos pela própria correção, além do formato de resposta com veredito `CORRIGIDO:` ou `FALHA:`.

#### Scenario: Relatório injetado
- **WHEN** o prompt é construído para um relatório
- **THEN** o texto contém o Markdown completo do relatório e nenhum marcador `{report_markdown}` remanescente

### Requirement: Parsing do veredito
O status final SHALL ser decidido pelas linhas de veredito da resposta do agente, procuradas em qualquer linha e ancoradas no início da linha (tolerando prefixos Markdown `-`, `*`, `#`, `>` e ênfase). Qualquer linha `FALHA:` MUST resultar em FALHA_CORRECAO. CORRIGIDO MUST ocorrer só quando houver ao menos uma linha `CORRIGIDO:` e nenhuma `FALHA:`. Sem nenhuma linha de veredito, o resultado MUST ser FALHA_CORRECAO com warning no log. Menções no meio de frase MUST ser ignoradas.

#### Scenario: Veredito após prosa
- **WHEN** a resposta tem um parágrafo de resumo e depois a linha `CORRIGIDO: imagem ajustada`
- **THEN** o resultado é CORRIGIDO

#### Scenario: Vereditos conflitantes
- **WHEN** a resposta contém uma linha `FALHA: pod em CrashLoop` e outra `CORRIGIDO: imagem ajustada`
- **THEN** o resultado é FALHA_CORRECAO

#### Scenario: Veredito com marcação
- **WHEN** a linha de veredito é `**CORRIGIDO:** imagem ajustada`
- **THEN** o resultado é CORRIGIDO

#### Scenario: Menção no meio de frase
- **WHEN** a única ocorrência é "o status CORRIGIDO: depende da validação" no meio de uma linha
- **THEN** o resultado é FALHA_CORRECAO com warning

#### Scenario: Limite de iterações atingido
- **WHEN** o run termina pelo limite de iterações sem linha de veredito
- **THEN** o resultado é FALHA_CORRECAO

### Requirement: Saída de CORRIGINDO só com o agente parado
Um relatório SHALL sair de CORRIGINDO somente depois que o agente que o corrigia tiver parado. A execução do agente MUST rodar sob timeout de `CORRECTION_TIMEOUT_MINUTES`; ao estourar, a task MUST ser cancelada e o relatório ir para FALHA_CORRECAO. Qualquer exceção na correção MUST levar a FALHA_CORRECAO.

#### Scenario: Timeout cancela o agente
- **WHEN** o agente não termina dentro de `CORRECTION_TIMEOUT_MINUTES`
- **THEN** a execução é cancelada e o relatório passa a FALHA_CORRECAO

#### Scenario: MCP indisponível
- **WHEN** o MCP Server não responde à conexão no início da correção
- **THEN** o relatório passa a FALHA_CORRECAO

#### Scenario: Exceção não prevista
- **WHEN** o agente levanta uma exceção qualquer
- **THEN** o relatório passa a FALHA_CORRECAO

### Requirement: Gravação final condicional
A transição de saída (CORRIGIDO ou FALHA_CORRECAO) SHALL ser um `UPDATE` condicional a `status='CORRIGINDO'`, com retry com backoff em erro transitório de banco (`OperationalError`, `InterfaceError`, `OSError`). Na transição para CORRIGIDO, `corrected_at` MUST receber o instante da transição; FALHA_CORRECAO MUST não alterar `corrected_at`. Se o relatório já tiver saído de CORRIGINDO, o resultado MUST ser descartado com warning.

#### Scenario: Sucesso preenche corrected_at
- **WHEN** o veredito é CORRIGIDO
- **THEN** o relatório passa a CORRIGIDO com `corrected_at` preenchido

#### Scenario: Falha preserva corrected_at
- **WHEN** o veredito é FALHA_CORRECAO
- **THEN** `corrected_at` permanece com o valor anterior

#### Scenario: Escritor atrasado
- **WHEN** a correção termina e o relatório já foi marcado FALHA_CORRECAO por outro caminho
- **THEN** o resultado da correção é descartado e o status não muda

#### Scenario: Banco oscilando
- **WHEN** a primeira tentativa de gravação falha com `OperationalError` e a segunda funciona
- **THEN** o status final é gravado

### Requirement: Resultado da correção sempre registrado
Toda saída de CORRIGINDO SHALL preencher `correction_result`: com a resposta do agente quando houver; senão, com mensagem fixa por causa:
- timeout: "Tempo limite atingido após N min; ações parciais podem ter sido aplicadas no cluster — verifique antes de tentar novamente";
- exceção: "Correção interrompida por erro: <mensagem>; ações parciais podem ter sido aplicadas no cluster";
- órfão no startup ou estagnação: "Correção interrompida (reinício da aplicação ou estagnação); ações parciais podem ter sido aplicadas no cluster".

#### Scenario: Resposta do agente gravada
- **WHEN** o agente responde com veredito e seção "Ações Executadas"
- **THEN** `correction_result` contém a resposta completa do agente

#### Scenario: Mensagem de timeout
- **WHEN** a correção é cancelada por timeout
- **THEN** `correction_result` contém a mensagem de tempo limite com o número de minutos

### Requirement: Recuperação de correções órfãs no startup
No startup, antes de servir requisições, o sistema SHALL marcar como FALHA_CORRECAO todo relatório CORRIGINDO, com a mensagem fixa de interrupção em `correction_result`. Falha de banco nessa etapa MUST ser registrada no log sem impedir o startup.

#### Scenario: Órfão após restart
- **WHEN** a aplicação inicia com um relatório em CORRIGINDO
- **THEN** o relatório passa a FALHA_CORRECAO e o botão "Executar correção" volta a aparecer no detalhe

### Requirement: Varredura de correções estagnadas
A cada lote processado pelo handler de análise, na mesma transação da varredura de estagnação de análises, o sistema SHALL marcar como FALHA_CORRECAO todo relatório CORRIGINDO com `correction_started_at` anterior a `agora − 2 × CORRECTION_TIMEOUT_MINUTES`, com a mensagem fixa de interrupção em `correction_result`.

#### Scenario: Correção estagnada
- **WHEN** um relatório está CORRIGINDO com `correction_started_at` há mais de 2× o timeout e o handler de análise processa um lote
- **THEN** o relatório passa a FALHA_CORRECAO

#### Scenario: Correção dentro do limite
- **WHEN** um relatório está CORRIGINDO com `correction_started_at` há menos de 2× o timeout
- **THEN** o relatório permanece CORRIGINDO

### Requirement: Correção dos cenários de referência
Com os manifestos de `manifestos-k8s/` aplicados no cluster kind `aiops` (`nginx.yaml` em `teste-a`, `kube-news.yaml` em `teste-b`) e os relatórios COMPLETO produzidos pela análise real, o acionamento de `POST /reports/{id}/fix` SHALL levar cada relatório a CORRIGIDO e deixar o cluster saudável, sem destruir a configuração existente dos deployments.

#### Scenario: Imagem inexistente do nginx
- **WHEN** a correção é acionada para o relatório COMPLETO de `teste-a/nginx` (imagem `ngin:latest`)
- **THEN** o relatório termina CORRIGIDO com `corrected_at` e `correction_result` preenchidos, o deployment `nginx` deixa de usar `ngin:latest`, preserva `containerPort` 80 e fica com todas as réplicas disponíveis e os pods Running e Ready

#### Scenario: Senha divergente do kube-news
- **WHEN** a correção é acionada para o relatório COMPLETO de `teste-b/kubenews` (`DB_PASSWORD=pg123` contra `POSTGRES_PASSWORD=pg1234`)
- **THEN** o relatório termina CORRIGIDO, `DB_PASSWORD` do `kubenews` passa a ser igual a `POSTGRES_PASSWORD` do `postgre`, a imagem `fabricioveronez/kube-news:v1`, as variáveis `DB_HOST`, `DB_DATABASE` e `DB_USERNAME` e as 10 réplicas são preservadas, e todas as réplicas ficam Running e Ready

#### Scenario: Interface reflete a correção
- **WHEN** a correção de um cenário de referência termina
- **THEN** `GET /reports` mostra o relatório com `badge-executed`, o detalhe exibe a seção "Resultado da Correção" sem o botão "Executar correção", e um novo `POST /reports/{id}/fix` responde `303` com `?erro=status_invalido`

### Requirement: Coluna correction_started_at
A tabela `reports` SHALL ter a coluna `correction_started_at` (timestamp com fuso, nula), criada por nova migration Alembic, preenchida a cada transição para CORRIGINDO.

#### Scenario: Migration adiciona a coluna
- **WHEN** `uv run alembic upgrade head` é executado sobre o schema do PRD 002
- **THEN** `reports.correction_started_at` existe e os relatórios existentes ficam com o valor nulo
