# local-validation Specification

## Purpose
TBD - Validação local com Compose e kind.

## Requirements

### Requirement: Cluster kind com port mapping do nodePort
O projeto SHALL ter um `k8s/kind-config.yaml` que cria um cluster kind com `extraPortMappings` do nodePort 30080 para a porta 8081 do host, para não conflitar com a porta 8080 usada pelo Compose.

#### Scenario: Compose e kind ao mesmo tempo
- **WHEN** o ambiente do Compose e o cluster kind estão rodando simultaneamente
- **THEN** a app do Compose responde em `localhost:8080` e a do kind em `localhost:8081`

### Requirement: Imagem carregada no kind sem registry
A validação no kind SHALL usar a imagem de produção carregada com `kind load docker-image`, com a mesma tag SemVer do manifesto, sem push prévio ao Docker Hub e sem alterar `imagePullPolicy` no manifesto.

#### Scenario: Pod usa a imagem local
- **WHEN** a imagem foi buildada e carregada no kind e o manifesto é aplicado
- **THEN** os pods da app sobem sem erro de pull (`ErrImagePull`/`ImagePullBackOff`)

### Requirement: Comunicação com o cluster só pelo MCP Kubernetes
Toda leitura e escrita no cluster (apply, get, describe, logs, delete) MUST passar pelo MCP Kubernetes, nunca por `kubectl` direto. Antes de qualquer apply, o contexto ativo MUST ser conferido como o do cluster kind.

#### Scenario: Apply no cluster correto
- **WHEN** o manifesto vai ser aplicado na validação local
- **THEN** o contexto ativo no MCP é `kind-kube-news` e o apply é feito pelo MCP

### Requirement: Checklist de validação do Compose
O ambiente de dev SHALL ser considerado validado só depois de passar em todos os itens: subida sem erro, conexão com o PG 18, criação e listagem de notícia, persistência após `down`/`up` e hot-reload após alterar um arquivo.

#### Scenario: Compose validado
- **WHEN** todos os itens do checklist do Compose foram executados
- **THEN** cada item tem resultado registrado como aprovado, com a evidência (comando e saída)

### Requirement: Checklist de validação no kind
O manifesto e a imagem de produção SHALL ser considerados validados só depois de passar em todos os itens no kind: rollout 2/2, app acessível em `localhost:8081`, balanceamento (o `machine` de `/health` alterna entre os dois pods em requisições novas), readiness tirando um pod do Service, liveness reiniciando um pod, e o procedimento de restart do banco (os dados somem e a app volta a funcionar depois de reiniciada).

#### Scenario: kind validado
- **WHEN** todos os itens do checklist do kind foram executados
- **THEN** cada item tem resultado registrado como aprovado, com a evidência (chamada ao MCP ou comando e saída)

#### Scenario: Restart do banco
- **WHEN** o pod do PostgreSQL é deletado e recriado
- **THEN** as notícias anteriores não existem mais, e depois do restart do Deployment da app ela volta a criar e listar notícias
