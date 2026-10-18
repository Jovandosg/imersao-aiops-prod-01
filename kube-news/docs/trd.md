# TRD — Technical Requirements Document

> Documento técnico global do projeto. Criado e atualizado via skill `escrever-trd`.
> Carregado automaticamente por `preparar-execucao` e `implementar-task` como contexto global.
> Granularidade baixa: cobre o que é global e estável. Regras finas ficam em ADRs.
>
> **Origem:** `docs/brainstorm-docker-kubernetes.md` (sessão de 2026-10-18). O projeto ainda não tem código: stack de aplicação extraída do `README.md`, infraestrutura extraída do brainstorm.

---

## Stack

| Dimensão | Valor |
|---|---|
| Linguagem principal | JavaScript (Node.js) |
| Runtime / plataforma | Node.js 24 (active LTS, EOL 30/04/2028 — verificado em 2026-10-18, [endoflife.ai](https://endoflife.ai/article-nodejs-eol.html)) |
| Framework principal | Express.js, com EJS como motor de templates *(do README; versão a definir na implementação)* |
| Banco de dados | PostgreSQL 18 (estável atual, suporte até ~11/2030 pela política de 5 anos — verificado em 2026-10-18, [postgresql.org](https://www.postgresql.org/about/news/postgresql-19-rc-1-released-3409/)), acessado via Sequelize ORM |
| Ferramentas de build | Docker: `Dockerfile` (produção) e `Dockerfile.dev` (desenvolvimento) — ver [ADR 006](adrs/006-dockerfiles-separados-prod-e-dev.md) |
| Gerenciador de pacotes | npm *(premissa — confirme ou corrija)* |
| Orquestração | Kubernetes — DigitalOcean Kubernetes (DOKS), manifesto agnóstico de provedor — ver [ADR 004](adrs/004-manifesto-kubernetes-agnostico.md) |
| Ambiente de desenvolvimento | Docker Compose (app + PostgreSQL 18) |
| Registry de imagens | Docker Hub, imagem pública `fabricioveronez/kube-news-aiops` — ver [ADR 005](adrs/005-docker-hub-publico-com-tag-imutavel.md) |

---

## Arquitetura

### Padrão arquitetural

Monólito web MVC server-side (Express + EJS + Sequelize) com um único banco relacional, empacotado em uma imagem de container.

O projeto é didático: existe para demonstrar containers e Kubernetes. Por isso a infraestrutura privilegia simplicidade e legibilidade em vez de práticas de produção que escondem o mecanismo.

### Ambientes

| Ambiente | Onde roda | Banco | Persistência | Exposição |
|---|---|---|---|---|
| Desenvolvimento local | Docker Compose | PostgreSQL 18 em container | Volume nomeado em `/var/lib/postgresql` | Porta local |
| Cloud (único, didático e descartável) | DOKS | PostgreSQL 18 no cluster | Nenhuma — ver [ADR 003](adrs/003-postgres-no-cluster-sem-persistencia.md) | `Service type: LoadBalancer`, HTTP — ver [ADR 001](adrs/001-exposicao-via-service-loadbalancer.md) |

Não existe staging, nem pipeline de CI/CD, nem GitOps. O deploy é manual — ver [ADR 007](adrs/007-deploy-manual-via-mcp-kubernetes.md).

### Topologia no Kubernetes

```
Internet ──HTTP──▶ Service kube-news (LoadBalancer)
                        │
                        ▼
                Deployment kube-news (2 réplicas)
                  env inline (sem ConfigMap/Secret)
                        │
                        ▼
                Service postgres (ClusterIP, só interno)
                        │
                        ▼
                Deployment postgres (1 réplica, Recreate, sem volume)
```

### Estrutura de pastas dominante

```
kube-news/
├── src/                 # código da aplicação, Dockerfile, Dockerfile.dev e .dockerignore (contexto de build)
│   ├── models/          # modelos Sequelize
│   ├── views/           # templates EJS
│   └── static/          # CSS e imagens
├── k8s/                 # manifesto Kubernetes único e agnóstico
├── docker-compose.yml   # ambiente de desenvolvimento local
└── docs/                # brainstorm, TRD e ADRs
```

*(premissa — confirme ou corrija: estrutura do README + defaults da skill `containerizar-docker`)*

### Módulos / camadas principais

| Módulo | Responsabilidade |
|---|---|
| `server` | Ponto de entrada Express: rotas web, API REST de inserção em massa, sync do schema |
| `models` | Modelo `Post` (Sequelize) |
| `views` | Páginas EJS (listagem, criação, visualização) |
| `system-life` | Endpoints `/health`, `/ready` e de simulação de falha (`/unhealth`, `/unreadyfor/:seconds`) |
| `middleware` | Middlewares da aplicação, incluindo o efeito do estado "não saudável" |
| Métricas | `/metrics` para Prometheus via express-prom-bundle |

---

## Requisitos Não-Funcionais

| Dimensão | Requisito |
|---|---|
| Performance | Não definido — volume de demonstração |
| Disponibilidade / SLA | Sem SLA. A app roda com 2 réplicas para demonstrar balanceamento e readiness. O banco tem 1 réplica sem persistência: RPO e RTO não se aplicam, e a perda total de dados (inclusive o schema) é aceita. Depois de um restart do banco, a app precisa ser reiniciada *(premissa — confirme ou corrija)* |
| Escalabilidade | Não definido — escala de demonstração |
| Segurança | Ambiente didático e descartável. Riscos aceitos de forma consciente: só HTTP (sem TLS), credenciais do banco em texto puro no manifesto ([ADR 002](adrs/002-configuracao-via-env-inline-sem-configmap-secret.md)) e rotas de simulação de falha públicas ([ADR 008](adrs/008-rotas-de-simulacao-de-falha-publicas.md)). O banco nunca é exposto fora do cluster (só `ClusterIP`). A aplicação não tem autenticação |
| Observabilidade | Probes de liveness em `/health` e de readiness em `/ready`. Métricas Prometheus em `/metrics`. Sem stack de observabilidade definida no cluster |
| Portabilidade | O manifesto Kubernetes usa só APIs core, sem annotations nem `storageClassName` da DigitalOcean ([ADR 004](adrs/004-manifesto-kubernetes-agnostico.md)) |
| Imagem | Tag imutável (SemVer), nunca `latest` ([ADR 005](adrs/005-docker-hub-publico-com-tag-imutavel.md)) |

---

## Dependências Externas

| Serviço / Sistema | Tipo | Constraint relevante | Dono |
|---|---|---|---|
| Docker Hub (`fabricioveronez/kube-news-aiops`, `postgres:18`) | Registry de imagens | Pull anônimo limitado a 100 a cada 6h por IP ([Docker Docs](https://docs.docker.com/docker-hub/usage/pulls/), 2026-10-18). Irrelevante para a escala do projeto, o que o usuário confirmou | externo |
| DigitalOcean Kubernetes (DOKS) | Cluster gerenciado | O Load Balancer da DO é provisionado pelo cloud controller a partir de `Service type: LoadBalancer`; ajustes específicos são por annotation, não usada aqui ([DO docs](https://docs.digitalocean.com/products/kubernetes/how-to/add-load-balancers/index.html.md), 2026-10-18). A StorageClass padrão é `do-block-storage`, só RWO (não usada no cluster) | externo |
| Imagem oficial `postgres` 18 | Imagem base | A partir do 18, `PGDATA=/var/lib/postgresql/18/docker` e o volume é montado em `/var/lib/postgresql`. Montar em `/var/lib/postgresql/data` falha na subida ([Docker Hub](https://hub.docker.com/_/postgres/), 2026-10-18). Afeta o Compose de dev | externo |
| MCP Kubernetes (`mcp-server-kubernetes`) | Ferramenta de operação | Único canal de acesso ao cluster; `kubectl` direto é proibido (`CLAUDE.md`) | externo |

---

## Padrões

### Testes

| Item | Valor |
|---|---|
| Framework | Não definido |
| Comando completo | Não definido |
| Cobertura mínima | Não definida |
| Estratégia | Não definida para a aplicação. Para a infraestrutura, a validação é por checklist com evidência real: rollout, balanceamento entre réplicas, readiness tirando o pod do Service, liveness reiniciando o pod, fluxo funcional (criar e listar post) |

### Estilo de código

- **Linter:** Não definido
- **Formatter:** Não definido
- **Convenções de nomenclatura:** Não definidas

### Containers e Kubernetes

- **Dois Dockerfiles** em `src/`, ambos com Node.js 24 — [ADR 006](adrs/006-dockerfiles-separados-prod-e-dev.md):
  - `Dockerfile` — produção, enxuto. É o que gera a imagem publicada;
  - `Dockerfile.dev` — desenvolvimento, com hot-reload e código montado como volume. É o que o Compose usa.
  A versão do Node e a instalação de dependências precisam ficar em sincronia entre os dois. O `Dockerfile` de produção deve ser buildado e validado antes de cada deploy, porque não é exercitado no dia a dia.
- **Manifesto Kubernetes único** em `k8s/`, só com APIs core — [ADR 004](adrs/004-manifesto-kubernetes-agnostico.md).
- **Sem ConfigMap, sem Secret, sem Ingress.** A configuração vai como `env` inline — [ADR 002](adrs/002-configuracao-via-env-inline-sem-configmap-secret.md).
- **A credencial do banco é duplicada** no Deployment da app e no do banco. Mudar uma exige mudar a outra.
- **Variáveis da aplicação** (do README): `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSL_REQUIRE`.

### Error handling

Não definido.

### Logging

- **Formato:** Não definido
- **Nível padrão:** Não definido
- **Biblioteca:** Não definida

### Autenticação / autorização

Não aplicável. A aplicação não tem autenticação e as rotas de simulação de falha são públicas por decisão didática ([ADR 008](adrs/008-rotas-de-simulacao-de-falha-publicas.md)).

### Pontos em aberto

- **Compatibilidade do Sequelize/`pg` com o PostgreSQL 18.** Nenhum dos dois declara suporte explícito (o Sequelize 6 declara "PostgreSQL ≥ 9.5" — [sequelize.org](https://sequelize.org/releases/), 2026-10-18). Destrava com um teste da aplicação contra o PG 18.
- **A skill `deploy-kubernetes` contradiz os ADRs 001–004** (gera Secret, ConfigMap, StatefulSet com volume, NodePort e kind). Ao usá-la, sobreponha os defaults ou adapte a skill.
- **Porta da aplicação:** o README indica `8080`; o `popula-dados.http` usa `4503`. Confirmar na implementação.

---

## Decisões Globais (ADRs)

| # | Título | Data | Status | Link |
|---|--------|------|--------|------|
| 001 | Exposição via Service LoadBalancer, sem Ingress | 2026-10-18 | aceito | [adrs/001-exposicao-via-service-loadbalancer.md](adrs/001-exposicao-via-service-loadbalancer.md) |
| 002 | Configuração via env inline, sem ConfigMap e Secret | 2026-10-18 | aceito | [adrs/002-configuracao-via-env-inline-sem-configmap-secret.md](adrs/002-configuracao-via-env-inline-sem-configmap-secret.md) |
| 003 | PostgreSQL 18 no cluster, sem persistência | 2026-10-18 | aceito | [adrs/003-postgres-no-cluster-sem-persistencia.md](adrs/003-postgres-no-cluster-sem-persistencia.md) |
| 004 | Manifesto Kubernetes agnóstico de provedor | 2026-10-18 | aceito | [adrs/004-manifesto-kubernetes-agnostico.md](adrs/004-manifesto-kubernetes-agnostico.md) |
| 005 | Docker Hub público com tag imutável | 2026-10-18 | aceito | [adrs/005-docker-hub-publico-com-tag-imutavel.md](adrs/005-docker-hub-publico-com-tag-imutavel.md) |
| 006 | Dockerfiles separados para produção e desenvolvimento, com Docker Compose no dev | 2026-10-18 | aceito | [adrs/006-dockerfiles-separados-prod-e-dev.md](adrs/006-dockerfiles-separados-prod-e-dev.md) |
| 007 | Deploy manual via MCP Kubernetes | 2026-10-18 | aceito | [adrs/007-deploy-manual-via-mcp-kubernetes.md](adrs/007-deploy-manual-via-mcp-kubernetes.md) |
| 008 | Rotas de simulação de falha ativas e públicas | 2026-10-18 | aceito | [adrs/008-rotas-de-simulacao-de-falha-publicas.md](adrs/008-rotas-de-simulacao-de-falha-publicas.md) |
| 009 | Validação local em kind via NodePort fixo no Service LoadBalancer | 2026-10-18 | aceito | [adrs/009-validacao-local-kind-nodeport.md](adrs/009-validacao-local-kind-nodeport.md) |
