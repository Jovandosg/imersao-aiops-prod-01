# kubernetes-manifest Specification

## Purpose
TBD - Manifesto Kubernetes único e agnóstico de provedor da aplicação.

## Requirements

### Requirement: Manifesto único e agnóstico de provedor
Toda a aplicação SHALL ser descrita num único arquivo `k8s/kube-news.yaml` que usa só APIs core do Kubernetes. O manifesto MUST NOT conter annotations de provedor nem `storageClassName`, e MUST NOT conter ConfigMap, Secret ou Ingress.

#### Scenario: Mesmo arquivo em clusters diferentes
- **WHEN** o manifesto é aplicado num cluster kind e num cluster DOKS
- **THEN** o arquivo aplicado é byte a byte o mesmo nos dois casos

#### Scenario: Ausência de objetos proibidos
- **WHEN** os `kind:` do manifesto são listados
- **THEN** não aparece `ConfigMap`, `Secret` nem `Ingress`, e nenhum objeto tem annotation de provedor

### Requirement: Namespace dedicado
Todos os objetos da aplicação SHALL ficar num Namespace próprio, declarado no próprio manifesto.

#### Scenario: Objetos isolados
- **WHEN** o manifesto é aplicado
- **THEN** o Namespace é criado e todos os Deployments e Services ficam dentro dele

### Requirement: PostgreSQL 18 sem persistência
O banco SHALL rodar como `Deployment` de 1 réplica com `strategy: Recreate`, imagem `postgres:18-alpine`, sem volume persistente, configurado por `env` inline, com readiness e liveness baseadas em `pg_isready`. O banco MUST ser exposto só por um Service `ClusterIP`.

#### Scenario: Banco inacessível de fora do cluster
- **WHEN** os Services do namespace são listados
- **THEN** o Service do banco é do tipo `ClusterIP`

#### Scenario: Atualização sem dois bancos simultâneos
- **WHEN** o Deployment do banco é atualizado
- **THEN** o pod antigo termina antes de o novo ser criado

### Requirement: Aplicação com 2 réplicas, probes e env inline
A aplicação SHALL rodar como `Deployment` de 2 réplicas, com readiness em `GET /ready` e liveness em `GET /health` na porta 8080, `resources` (requests e limits) declarados e configuração `DB_*` por `env` inline com valores iguais aos do banco. Valores com caracteres especiais (como a senha) MUST estar entre aspas no YAML.

#### Scenario: Rollout saudável
- **WHEN** o manifesto é aplicado com o banco disponível
- **THEN** o Deployment da app chega a 2/2 réplicas Ready

#### Scenario: Readiness tira o pod do Service
- **WHEN** `PUT /unreadyfor/60` é enviado a um pod da app
- **THEN** esse pod sai dos endpoints do Service enquanto `/ready` falha, e o tráfego segue no outro pod

#### Scenario: Liveness reinicia o pod
- **WHEN** `PUT /unhealth` é enviado a um pod da app
- **THEN** o kubelet reinicia o container desse pod e o contador de restarts aumenta

### Requirement: App aguarda o banco antes de iniciar
O Deployment da app SHALL ter um initContainer que bloqueia a inicialização até o Service do banco aceitar conexões (`pg_isready`).

#### Scenario: App aplicada antes de o banco ficar pronto
- **WHEN** o manifesto é aplicado num namespace vazio
- **THEN** os pods da app ficam em `Init` até o banco ficar pronto e não entram em `CrashLoopBackOff` por banco indisponível

### Requirement: Exposição por LoadBalancer com nodePort fixo
A aplicação SHALL ser exposta por um Service `type: LoadBalancer` na porta 80, com `targetPort` 8080 e `nodePort` fixo (30080), em HTTP.

#### Scenario: Acesso em cluster com cloud controller
- **WHEN** o manifesto é aplicado na DOKS
- **THEN** o Service recebe um `EXTERNAL-IP` e a app responde por HTTP na porta 80 desse IP

#### Scenario: Acesso em cluster sem cloud controller
- **WHEN** o manifesto é aplicado no kind
- **THEN** o `EXTERNAL-IP` fica `<pending>` e a app responde pelo nodePort 30080 dos nodes
