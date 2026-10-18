## ADDED Requirements

### Requirement: Modelo persistido de relatórios
O sistema SHALL persistir relatórios no PostgreSQL na tabela `reports`, criada por migration Alembic, com as colunas `id` (UUID, chave primária), `markdown` (texto, nulo), `status` (texto, não nulo), `event_uids` (`TEXT[]`, não nulo, com índice GIN), `severity` (texto, nulo), `namespace` (texto, nulo), `title` (texto, nulo), `created_at` e `updated_at` (timestamp com fuso, não nulos) e `corrected_at` e `correction_result` (nulos). `status` MUST assumir apenas EM_ANALISE, COMPLETO, INCOMPLETO, CORRIGINDO, CORRIGIDO ou FALHA_CORRECAO. Toda alteração de linha MUST atualizar `updated_at`.

#### Scenario: Migration cria a tabela
- **WHEN** `uv run alembic upgrade head` é executado num banco vazio
- **THEN** a tabela `reports` existe com todas as colunas listadas e um índice GIN sobre `event_uids`

#### Scenario: Status inválido é rejeitado
- **WHEN** se tenta gravar um relatório com status fora dos seis valores permitidos
- **THEN** a gravação falha

#### Scenario: Atualização avança updated_at
- **WHEN** o status de um relatório é alterado
- **THEN** `updated_at` passa a ser o instante da alteração e `created_at` permanece inalterado

### Requirement: Deduplicação de eventos por uid
Antes de qualquer análise, o sistema SHALL remover do lote os eventos cujo `uid` esteja bloqueado. Um uid está bloqueado quando existe ao menos um relatório que contém o uid em `event_uids` e se encontra em uma destas situações:
- status EM_ANALISE, COMPLETO, CORRIGINDO ou FALHA_CORRECAO;
- status CORRIGIDO, com `timestamp` do evento menor ou igual a `corrected_at` (ou a `updated_at`, quando `corrected_at` é nulo);
- status INCOMPLETO, com `created_at` mais recente que `agora - ANALYSIS_RETRY_COOLDOWN_MINUTES`.

A decisão MUST considerar todos os relatórios que contêm o uid, nunca apenas o mais recente. Um uid sem nenhum relatório MUST ser liberado.

#### Scenario: Evento novo é liberado
- **WHEN** chega um evento cujo uid não aparece em nenhum relatório
- **THEN** o evento segue para a análise

#### Scenario: Evento em tratamento é ignorado
- **WHEN** o uid de um evento consta de um relatório EM_ANALISE, COMPLETO, CORRIGINDO ou FALHA_CORRECAO
- **THEN** o evento é removido do lote

#### Scenario: Reentrega após correção é ignorada
- **WHEN** o uid consta de um relatório CORRIGIDO e o `timestamp` do evento é anterior a `corrected_at`
- **THEN** o evento é removido do lote

#### Scenario: Reincidência após correção é reanalisada
- **WHEN** o uid consta de um relatório CORRIGIDO e o `timestamp` do evento é posterior a `corrected_at`
- **THEN** o evento segue para a análise

#### Scenario: INCOMPLETO dentro do cooldown é ignorado
- **WHEN** o uid consta de um relatório INCOMPLETO criado há menos de `ANALYSIS_RETRY_COOLDOWN_MINUTES`
- **THEN** o evento é removido do lote

#### Scenario: INCOMPLETO fora do cooldown é reanalisado
- **WHEN** o uid consta apenas de um relatório INCOMPLETO criado há mais de `ANALYSIS_RETRY_COOLDOWN_MINUTES`
- **THEN** o evento segue para a análise

#### Scenario: Relatório ativo prevalece sobre um antigo liberado
- **WHEN** o uid consta de um relatório CORRIGIDO antigo cuja condição o liberaria e também de um relatório EM_ANALISE
- **THEN** o evento é removido do lote

#### Scenario: Lote parcialmente em tratamento
- **WHEN** um lote tem três eventos e apenas um deles está bloqueado
- **THEN** somente os dois eventos liberados seguem para a análise

#### Scenario: Lote inteiramente em tratamento
- **WHEN** todos os eventos do lote estão bloqueados
- **THEN** nenhum relatório é criado e nenhuma análise é disparada

### Requirement: Timeout de estagnação de análises
Durante a deduplicação, e antes de avaliar os bloqueios, o sistema SHALL marcar como INCOMPLETO todo relatório EM_ANALISE com `created_at` mais antigo que `agora - ANALYSIS_STALE_TIMEOUT_MINUTES`.

#### Scenario: Análise estagnada é liberada
- **WHEN** existe um relatório EM_ANALISE criado há mais de `ANALYSIS_STALE_TIMEOUT_MINUTES` e um lote chega
- **THEN** o relatório passa a INCOMPLETO antes da avaliação de bloqueios do lote

#### Scenario: Análise recente não é afetada
- **WHEN** existe um relatório EM_ANALISE criado há menos de `ANALYSIS_STALE_TIMEOUT_MINUTES`
- **THEN** o relatório permanece EM_ANALISE

### Requirement: Registro EM_ANALISE antes da análise
Para cada lote com ao menos um evento liberado, o sistema SHALL gravar um único relatório com status EM_ANALISE, `markdown` nulo e `event_uids` igual aos uids liberados, e só depois invocar o analisador. A deduplicação e a gravação MUST acontecer na mesma transação.

#### Scenario: Ciclo seguinte ignora o lote em análise
- **WHEN** um lote é liberado e, enquanto sua análise roda, o coletor reentrega os mesmos eventos
- **THEN** a reentrega é removida pela deduplicação e nenhum novo relatório é criado

#### Scenario: Relatório gravado antes do analisador
- **WHEN** o analisador é invocado para um lote
- **THEN** já existe no banco um relatório EM_ANALISE com os uids desse lote

### Requirement: Entrega do lote ao analisador
Depois de gravar o relatório EM_ANALISE, o handler de análise SHALL entregar o id desse relatório e os eventos liberados ao analisador (capability `agente-analise`), fora da transação de deduplicação. Se o analisador lançar exceção, o handler MUST registrar o erro no log e marcar o relatório como INCOMPLETO, desde que ele ainda esteja em EM_ANALISE. Exceções MUST NOT propagar ao coletor.

#### Scenario: Analisador recebe só os eventos liberados
- **WHEN** um lote de três eventos tem um evento bloqueado
- **THEN** o analisador recebe o id do relatório EM_ANALISE e apenas os dois eventos liberados

#### Scenario: Falha do analisador
- **WHEN** o analisador lança uma exceção
- **THEN** o erro é registrado no log e o relatório passa a INCOMPLETO

#### Scenario: Relatório já recuperado não é sobrescrito
- **WHEN** o analisador falha depois que o relatório já foi movido para INCOMPLETO por estagnação
- **THEN** nenhuma transição adicional é aplicada a esse relatório

#### Scenario: Log do lote processado
- **WHEN** um lote é processado
- **THEN** o log registra a quantidade de eventos recebidos, a de bloqueados e, se houver, o id do relatório criado

### Requirement: Banco indisponível na deduplicação
Se o banco estiver indisponível durante a deduplicação ou a gravação do EM_ANALISE, o sistema SHALL registrar o erro no log e descartar o lote, sem propagar a exceção ao coletor.

#### Scenario: PostgreSQL fora do ar
- **WHEN** um lote chega e o PostgreSQL não responde
- **THEN** o erro é registrado no log, nenhum analisador é invocado e o loop de coleta continua

### Requirement: Recuperação de análises órfãs no startup
No startup da aplicação, o sistema SHALL marcar como INCOMPLETO todos os relatórios em EM_ANALISE. A recuperação MUST terminar antes da primeira coleta de eventos. Se o banco estiver indisponível no startup, o sistema MUST registrar o erro no log e iniciar normalmente, deixando os órfãos para o timeout de estagnação.

#### Scenario: Órfão após restart
- **WHEN** a aplicação inicia e existe um relatório EM_ANALISE de uma execução anterior
- **THEN** o relatório passa a INCOMPLETO antes da primeira coleta

#### Scenario: Ordem entre recuperação e coleta
- **WHEN** a aplicação inicia
- **THEN** a primeira chamada de listagem de eventos ocorre depois de a recuperação terminar

#### Scenario: Banco fora do ar no startup
- **WHEN** a aplicação inicia com o PostgreSQL indisponível
- **THEN** o erro é registrado no log e o coletor inicia mesmo assim

### Requirement: Parâmetros de deduplicação configuráveis
O sistema SHALL ler `ANALYSIS_RETRY_COOLDOWN_MINUTES` e `ANALYSIS_STALE_TIMEOUT_MINUTES`, em minutos, com padrão 30 para ambos. Valores não numéricos, zero ou negativos MUST resultar no padrão com warning no log. Valores fracionários positivos MUST ser aceitos.

#### Scenario: Valor inválido
- **WHEN** `ANALYSIS_RETRY_COOLDOWN_MINUTES` vale `abc`
- **THEN** o cooldown usado é de 30 minutos e um warning é registrado

#### Scenario: Valor fracionário
- **WHEN** `ANALYSIS_STALE_TIMEOUT_MINUTES` vale `0.5`
- **THEN** o timeout de estagnação usado é de 30 segundos
