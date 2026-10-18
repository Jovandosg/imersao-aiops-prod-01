## ADDED Requirements

### Requirement: Dockerfile de desenvolvimento com hot-reload
O projeto SHALL ter um `src/Dockerfile.dev` baseado em Node.js 24 que executa a aplicação com `node --watch`, para recarregar o processo quando o código muda, sem adicionar dependências ao `package.json`.

#### Scenario: Alteração de código recarrega a app
- **WHEN** o ambiente de dev está rodando e um arquivo `.js` em `src/` é alterado no host
- **THEN** o processo Node reinicia dentro do container e a alteração passa a valer sem rebuild da imagem

### Requirement: Compose com app e PostgreSQL 18
O projeto SHALL ter um `docker-compose.yml` na raiz com dois serviços: a app, buildada a partir de `src/Dockerfile.dev` com o código montado como volume, e o PostgreSQL 18 (`postgres:18-alpine`). A app MUST receber a configuração pelas variáveis `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD` e `DB_SSL_REQUIRE`.

#### Scenario: Subida do ambiente
- **WHEN** `docker compose up` é executado na raiz
- **THEN** a app responde em `http://localhost:8080` e consegue criar e listar notícias no PostgreSQL 18

### Requirement: App só sobe com o banco pronto
O serviço da app MUST depender do serviço do banco com a condição `service_healthy`, e o banco MUST ter um healthcheck baseado em `pg_isready`.

#### Scenario: Ordem de subida
- **WHEN** `docker compose up` é executado com os volumes vazios
- **THEN** a app só é iniciada depois que o healthcheck do Postgres passa, e o boot da app não falha por banco indisponível

### Requirement: Persistência dos dados de dev
O PostgreSQL do Compose MUST usar um volume nomeado montado em `/var/lib/postgresql`, que é o caminho exigido pela imagem oficial a partir do PG 18. O caminho legado `/var/lib/postgresql/data` MUST NOT ser usado.

#### Scenario: Dados sobrevivem a down/up
- **WHEN** uma notícia é criada, `docker compose down` (sem `-v`) é executado e depois `docker compose up`
- **THEN** a notícia continua listada
