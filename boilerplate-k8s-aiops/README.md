# Boilerplate: FastAPI + LangChain Agent + MCP

Boilerplate para criar agentes inteligentes com:

- **FastAPI** (async) como backend
- **LangChain + Claude Sonnet** como framework de agentes (padrao ReAct)
- **MCP Server** para integracao com ferramentas externas
- **PostgreSQL** + SQLAlchemy async para persistencia
- **Alembic** para migrations
- **Jinja2** para interface web com dark theme

## Como usar

### 1. Copiar o boilerplate

```bash
cp -r boilerplate/ ~/projetos/meu-novo-agente/
cd ~/projetos/meu-novo-agente/
```

### 2. Renomear o package

Renomeie `my_agent_app` para o nome do seu projeto em todos os arquivos:

```bash
# Renomear diretorio
mv src/my_agent_app src/meu_agente

# Substituir em todos os arquivos
find . -type f -name "*.py" -o -name "*.toml" -o -name "*.ini" -o -name "*.md" -o -name "*.html" | \
  xargs sed -i 's/my_agent_app/meu_agente/g; s/my-agent-app/meu-agente/g; s/My Agent App/Meu Agente/g'
```

### 3. Configurar ambiente

```bash
cp .env.example .env
# Edite .env com suas configuracoes (ANTHROPIC_API_KEY, etc)
```

### 4. Subir o banco de dados

O Docker provisiona **apenas o banco** (PostgreSQL + pgAdmin):

```bash
docker compose up -d
```

### 5. Instalar dependencias

```bash
uv sync
```

### 6. Subir o MCP Server (via npx)

O MCP Server Kubernetes roda localmente via `npx` expondo transport HTTP (streamable). Requer **Node.js/npx** instalado e um **kubeconfig** valido em `~/.kube/config`:

```bash
ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes
```

O agente LangChain conecta a esse servidor por HTTP em `http://localhost:3001/mcp` (`MCP_SERVER_URL`).

### 7. Executar

A aplicacao roda localmente via `uv`:

```bash
uv run uvicorn meu_agente.main:app --host 0.0.0.0 --port 8000
```

## Coleta de eventos Kubernetes

Ao subir, a aplicacao inicia um loop (`collector/`) que lista os eventos **Warning** de todos os namespaces via API `events.k8s.io/v1` a cada `EVENT_COLLECTION_INTERVAL_MINUTES` (padrao 3). A primeira coleta e imediata e entrega todos os Warnings ainda presentes no cluster; as seguintes usam uma marca d'agua em memoria com sobreposicao de um intervalo. Cada batch e despachado ao `AnalysisEventHandler` (`agents/`), que remove os eventos ja cobertos por relatorios, grava um relatorio EM_ANALISE e aciona o agente de causa raiz (LangChain + Claude, tools somente leitura do MCP Server). A resposta vira um relatorio por problema na tabela `reports`.

A autenticacao tenta o service account (in-cluster) e, em seguida, o kubeconfig local (`KUBECONFIG` ou `~/.kube/config`).

### Permissao minima (RBAC)

O coletor precisa apenas do verbo `list` em `events` do grupo `events.k8s.io`, em todos os namespaces:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aiops-event-collector
rules:
  - apiGroups: ["events.k8s.io"]
    resources: ["events"]
    verbs: ["list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: aiops-event-collector
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: aiops-event-collector
subjects:
  - kind: ServiceAccount
    name: aiops            # ajuste para o ServiceAccount da aplicacao
    namespace: aiops
```

Sem essa permissao, cada ciclo registra no log um erro HTTP 403 indicando a permissao faltante, e o loop continua.

### Premissa: instancia unica

Rode **uma unica instancia** da aplicacao por cluster. A marca d'agua fica em memoria e nao ha trava entre replicas: com varias replicas, cada uma coletaria e despacharia os mesmos eventos.

### Ambiente de teste com kind

```bash
# Setup
kind create cluster --name aiops
kubectl cluster-info --context kind-aiops
kubectl --context kind-aiops create namespace teste-a
kubectl --context kind-aiops create namespace teste-b
kubectl --context kind-aiops apply -n teste-a -f manifestos-k8s/nginx.yaml      # imagem inexistente -> Failed/BackOff
kubectl --context kind-aiops apply -n teste-b -f manifestos-k8s/kube-news.yaml  # senha errada do banco -> BackOff
kubectl --context kind-aiops get events -A --field-selector type=Warning

# Testes de integracao (pulam se o contexto ativo nao for kind-aiops)
kubectl config use-context kind-aiops
uv run pytest -m kind

# Banco + MCP Server (o MCP usa o contexto ativo: confira que e o kind-aiops)
docker compose up -d
uv run alembic upgrade head
ENABLE_UNSAFE_STREAMABLE_HTTP_TRANSPORT=1 PORT=3001 npx mcp-server-kubernetes   # outro terminal

# Testes de banco e fluxo completo (o e2e recria teste-a/teste-b e faz uma analise real na API Anthropic)
uv run pytest -m db
uv run pytest -m e2e

# Rodar a app contra o kind com coleta a cada 30s e cooldown curto de reanalise
EVENT_COLLECTION_INTERVAL_MINUTES=0.5 ANALYSIS_RETRY_COOLDOWN_MINUTES=2 uv run uvicorn my_agent_app.main:app --port 8000

# Conferir os relatorios
docker compose exec postgres psql -U aiops aiops_k8s -c "select status, severity, namespace, title from reports order by created_at"

# Teardown
kind delete cluster --name aiops
```

## Interface web e correcao automatica

Com a app no ar, `http://localhost:8000/reports` lista os relatorios (mais recente primeiro) e `/reports/{id}` mostra o detalhe com o Markdown convertido no servidor. Relatorios COMPLETO ou FALHA_CORRECAO exibem o botao **Executar correcao**: o `POST /reports/{id}/fix` move o relatorio para CORRIGINDO e dispara em background o agente de correcao, que tem **acesso irrestrito ao cluster** via MCP Server (todas as tools, inclusive escrita). Atualize a pagina para acompanhar; o resultado aparece na secao "Resultado da Correcao".

A correcao roda sob `CORRECTION_TIMEOUT_MINUTES` (padrao 10). Correcoes interrompidas por restart viram FALHA_CORRECAO no startup e podem ser acionadas de novo.

### Seed para validar a interface sem o agente

```bash
uv run alembic upgrade head
uv run python scripts/seed_reports.py   # um relatorio em cada um dos seis status (usa DATABASE_URL)
```

### Teste de ponta a ponta da correcao

Mesmos pre-requisitos do `uv run pytest -m e2e` acima: contexto ativo `kind-aiops`, PostgreSQL do docker compose, MCP Server em `MCP_SERVER_URL` e `ANTHROPIC_API_KEY` no `.env`. O teste recria `teste-a`/`teste-b`, aplica os manifestos, faz a analise real e aciona `POST /reports/{id}/fix` para o nginx e depois para o kube-news, conferindo banco, cluster e interface.

```bash
uv run pytest -m e2e tests/test_e2e_correcao.py
```

Custo por execucao: **uma analise e duas correcoes reais** na API Anthropic. Ao fim, o cluster fica com os cenarios corrigidos; a proxima execucao recria os namespaces. Na primeira execucao, as respostas do agente de correcao sao gravadas em `tests/fixtures/e2e_correction_responses.json` e passam a ser casos de `tests/test_verdict.py`.

## Estrutura

```
src/my_agent_app/
├── main.py              # FastAPI + lifespan
├── database.py          # Base declarativa + DATABASE_URL
├── api/router.py        # Health check
├── web/                 # Paginas de relatorios, POST /fix e render do Markdown (Jinja2)
├── templates/           # Templates HTML (dark theme)
├── agents/              # Analise (dedup, handler, prompt, parser, agente) e correcao (prompt, veredito, agente, executor)
├── collector/           # Loop de coleta de eventos Warning do Kubernetes
└── models/              # Report (ORM) e repositorio de transicoes
scripts/seed_reports.py  # Relatorios de exemplo em todos os status
```

## Stack

| Tecnologia | Uso |
|------------|-----|
| FastAPI + Uvicorn | Backend async |
| SQLAlchemy 2.0 + asyncpg | ORM async com PostgreSQL |
| Alembic | Migrations |
| LangChain + Claude Sonnet | Framework de agentes IA |
| MCP Server | Integracao com ferramentas externas |
| Jinja2 | Interface web server-side |
| Docker Compose | Banco de dados local (PostgreSQL + pgAdmin) |
| Node.js + npx | Runtime do MCP Server Kubernetes (transport HTTP) |
| UV + hatchling | Package manager + build system |
