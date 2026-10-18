# coleta-eventos Specification

## Purpose
Coleta periódica de eventos Warning do cluster Kubernetes, com janela temporal por marca d'água, contrato de saída do evento e despacho assíncrono ao `EventHandler`. Criada a partir da change coleta-eventos-kubernetes.

## Requirements

### Requirement: Coleta periódica de eventos Warning
O sistema SHALL executar, dentro do processo FastAPI, um loop assíncrono que lista eventos do cluster via Python SDK `kubernetes` (API `events.k8s.io/v1`) em todos os namespaces e considera apenas eventos com `type == "Warning"`. Eventos de qualquer outro tipo MUST ser ignorados.

#### Scenario: Apenas Warnings são entregues
- **WHEN** o cluster contém eventos Normal e Warning dentro da janela de coleta
- **THEN** o batch entregue ao handler contém somente os eventos Warning

#### Scenario: Todos os namespaces são cobertos
- **WHEN** existem eventos Warning nos namespaces `a`, `b` e `kube-system`
- **THEN** o batch entregue contém os eventos dos três namespaces

### Requirement: Coleta imediata e sem filtro temporal no startup
Ao iniciar a aplicação, o sistema SHALL executar a primeira coleta imediatamente, antes de aguardar o primeiro intervalo. Essa primeira coleta MUST NOT aplicar filtro de recência: todos os eventos Warning ainda presentes no cluster são entregues.

#### Scenario: Primeira coleta sem espera
- **WHEN** a aplicação inicia
- **THEN** uma coleta é executada sem aguardar `EVENT_COLLECTION_INTERVAL_MINUTES`

#### Scenario: Eventos anteriores ao start são recolhidos
- **WHEN** a aplicação inicia e o cluster contém um evento Warning de 40 minutos atrás que ainda não expirou
- **THEN** esse evento é incluído no batch da primeira coleta

### Requirement: Filtro de recência por marca d'água com sobreposição
A partir da segunda coleta, o sistema SHALL entregar apenas eventos cuja recência seja maior ou igual a `marca_dagua - margem_de_sobreposicao`, em que a marca d'água é o instante de início da última coleta bem-sucedida e a margem é igual a um intervalo de coleta. A marca d'água MUST ser capturada antes da chamada de listagem e MUST avançar após cada coleta bem-sucedida, independentemente do resultado do handler. A marca d'água MUST ser mantida em memória.

#### Scenario: Evento antigo é descartado
- **WHEN** um evento tem recência anterior a `marca_dagua - margem`
- **THEN** o evento não é entregue

#### Scenario: Evento visível com atraso dentro da margem é recolhido
- **WHEN** um evento com recência T anterior à marca d'água C, mas posterior a `C - margem`, só aparece na API depois da coleta que gravou C
- **THEN** o evento é entregue na coleta seguinte

#### Scenario: Falha na coleta não avança a marca d'água
- **WHEN** a listagem de eventos falha
- **THEN** a marca d'água permanece inalterada e a mesma janela é reconsultada no próximo ciclo

### Requirement: Precedência de timestamps para recência
O sistema SHALL determinar a recência de cada evento pela primeira opção presente, nesta ordem: `series.lastObservedTime`, `eventTime`, `deprecatedLastTimestamp`. Eventos sem nenhum dos três MUST ser descartados com warning no log.

#### Scenario: Evento recorrente usa series
- **WHEN** um evento tem `series.lastObservedTime` dentro da janela e `eventTime` anterior a ela
- **THEN** o evento é entregue e o `timestamp` do contrato é `series.lastObservedTime`

#### Scenario: Evento legado usa deprecatedLastTimestamp
- **WHEN** um evento não tem `series` nem `eventTime`, mas tem `deprecatedLastTimestamp`
- **THEN** a recência e o `timestamp` do contrato vêm de `deprecatedLastTimestamp`

#### Scenario: Evento sem timestamp é descartado
- **WHEN** um evento não tem `series.lastObservedTime`, `eventTime` nem `deprecatedLastTimestamp`
- **THEN** o evento é descartado e um warning é registrado no log

### Requirement: Contrato de saída do evento
Cada evento entregue ao handler SHALL ser um dict com as chaves `uid` (`metadata.uid`), `type`, `reason`, `message` (de `note`), `namespace`, `involved_object` (de `regarding`, com `kind`, `name` e `namespace`) e `timestamp` (string ISO 8601 conforme a precedência de recência). Para recursos cluster-scoped, `involved_object.namespace` MUST ser string vazia.

#### Scenario: Mapeamento a partir de events.k8s.io/v1
- **WHEN** um evento Warning com `note`, `regarding` e `metadata.uid` é coletado
- **THEN** o dict entregue contém exatamente as chaves do contrato, com `message` igual a `note` e `involved_object` derivado de `regarding`

#### Scenario: Recurso cluster-scoped
- **WHEN** o evento se refere a um Node
- **THEN** `involved_object.namespace` é `""`

### Requirement: Despacho assíncrono fire-and-forget ao EventHandler
O sistema SHALL agrupar todos os eventos de uma coleta em uma única lista, sem limite de quantidade, e despachá-la a `EventHandler.handle(events)` como task assíncrona, sem aguardar a conclusão. Exceções do handler MUST NOT propagar ao loop de coleta nem afetar a marca d'água. Quando a coleta não encontra eventos, o handler MUST NOT ser invocado.

#### Scenario: Coletor não bloqueia no handler
- **WHEN** o handler demora mais que um intervalo de coleta
- **THEN** o próximo ciclo de coleta é executado no horário previsto

#### Scenario: Erro no handler é isolado
- **WHEN** o handler lança uma exceção
- **THEN** a exceção é registrada no log, o loop continua e a marca d'água já avançou

#### Scenario: Nenhum evento
- **WHEN** a coleta não retorna eventos Warning na janela
- **THEN** o handler não é invocado

### Requirement: Exibição dos eventos coletados no stdout
A implementação placeholder do `EventHandler` SHALL imprimir no stdout cada batch recebido: um cabeçalho com a quantidade de eventos e o instante da coleta, seguido de uma linha por evento contendo todos os campos do contrato de saída (`uid`, `type`, `reason`, `message`, `namespace`, `involved_object.kind`, `involved_object.name`, `involved_object.namespace` e `timestamp`). A saída MUST ir para o stdout, não para o logger.

#### Scenario: Batch impresso
- **WHEN** o handler recebe um batch com 2 eventos
- **THEN** o stdout contém um cabeçalho indicando 2 eventos e duas linhas, cada uma com todos os campos do contrato

#### Scenario: Evento de pod com imagem inexistente visível no stdout
- **WHEN** o manifesto `manifestos-k8s/nginx.yaml` (imagem `ngin:latest`) é aplicado no cluster kind e a coleta roda
- **THEN** o stdout exibe eventos Warning do pod `nginx-*` com reason de falha de pull de imagem (por exemplo, `Failed` ou `BackOff`)

### Requirement: Intervalo configurável
O sistema SHALL ler o intervalo de coleta, em minutos, da env var `EVENT_COLLECTION_INTERVAL_MINUTES`, com padrão 3. Valores não numéricos, zero ou negativos MUST resultar no padrão com warning no log. Valores fracionários positivos MUST ser aceitos.

#### Scenario: Valor inválido
- **WHEN** `EVENT_COLLECTION_INTERVAL_MINUTES=abc`
- **THEN** o intervalo é 3 minutos e um warning é registrado

#### Scenario: Valor fracionário
- **WHEN** `EVENT_COLLECTION_INTERVAL_MINUTES=0.5`
- **THEN** o intervalo é 30 segundos

### Requirement: Resiliência a falhas do cluster
Falhas de conectividade ou de autorização (HTTP 401/403) durante a coleta SHALL ser registradas no log e MUST NOT interromper o loop. Em erro de RBAC, a mensagem MUST indicar a permissão necessária (`list` em `events.events.k8s.io` em todos os namespaces).

#### Scenario: Cluster inacessível
- **WHEN** o apiserver está inacessível durante um ciclo
- **THEN** o erro é registrado e o loop tenta novamente no ciclo seguinte

#### Scenario: Permissão insuficiente
- **WHEN** a listagem retorna 403
- **THEN** o log indica a permissão necessária e o loop continua

### Requirement: Autenticação com o cluster
O sistema SHALL tentar `load_incluster_config()` e, em caso de falha, `load_kube_config()`.

#### Scenario: Execução local
- **WHEN** a aplicação roda fora do cluster com `~/.kube/config` válido
- **THEN** a coleta autentica pelo kubeconfig
