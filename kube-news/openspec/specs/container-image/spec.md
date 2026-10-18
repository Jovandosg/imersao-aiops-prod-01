# container-image Specification

## Purpose
TBD - Imagem de container de produção da aplicação kube-news.

## Requirements

### Requirement: Imagem de produção a partir de Dockerfile dedicado
O projeto SHALL ter um `src/Dockerfile` de produção baseado em Node.js 24, independente do `Dockerfile.dev`, que instala apenas dependências de produção e inicia a aplicação com `node server.js`.

#### Scenario: Build da imagem de produção
- **WHEN** `docker build -t fabricioveronez/kube-news-aiops:<versão> src/` é executado com `src/` cumprindo o contrato da app
- **THEN** o build termina sem erro e a imagem resultante não contém `devDependencies`

#### Scenario: Container sobe e escuta na porta 8080
- **WHEN** a imagem é executada com as variáveis `DB_*` apontando para um PostgreSQL acessível
- **THEN** a aplicação responde `200` em `GET /health` na porta 8080

### Requirement: Execução como usuário não-root
O container de produção MUST executar o processo da aplicação com um usuário não-root.

#### Scenario: Usuário do processo
- **WHEN** o container de produção está rodando
- **THEN** o processo da aplicação não roda com UID 0

### Requirement: Encerramento por sinal
O container de produção SHALL repassar `SIGTERM` ao processo Node e encerrar dentro do período de graça padrão do Kubernetes (30s).

#### Scenario: docker stop encerra rápido
- **WHEN** `docker stop` é executado no container de produção
- **THEN** o container termina antes do timeout padrão de 10s, sem precisar de `SIGKILL`

### Requirement: Contexto de build enxuto
O projeto SHALL ter um `src/.dockerignore` que exclui do contexto de build pelo menos `node_modules`, arquivos de log e arquivos de ambiente local.

#### Scenario: node_modules local não entra na imagem
- **WHEN** existe um `src/node_modules` local e a imagem é buildada
- **THEN** o `node_modules` da imagem vem do `npm ci` no build, não do diretório local

### Requirement: Tag imutável e publicação no Docker Hub
A imagem SHALL ser publicada como `fabricioveronez/kube-news-aiops:<SemVer>` no Docker Hub público. A tag `latest` MUST NOT ser usada, nem no push nem no manifesto, e uma tag já publicada MUST NOT ser sobrescrita.

#### Scenario: Nova versão
- **WHEN** uma nova versão da imagem precisa ser publicada
- **THEN** ela recebe uma tag SemVer ainda não existente no repositório do Docker Hub

#### Scenario: Manifesto referencia tag fixa
- **WHEN** o manifesto Kubernetes é inspecionado
- **THEN** a imagem da app aparece com tag SemVer explícita, nunca `latest` nem sem tag
