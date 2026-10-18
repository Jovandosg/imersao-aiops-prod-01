## 1. Pré-requisito: contrato da aplicação

- [x] 1.1 Confirmar que `src/` existe com `package.json`, `package-lock.json` e `server.js` (bloqueia todos os grupos seguintes se faltar)
- [x] 1.2 Conferir o contrato do design item a item (porta 8080, `/health`, `/ready`, `/unhealth`, `/unreadyfor/:seconds`, variáveis `DB_*`, schema criado no boot) e registrar divergências no `design.md`

## 2. Imagem de produção

- [x] 2.1 Criar `src/.dockerignore` excluindo `node_modules`, logs e arquivos de ambiente local
- [x] 2.2 Criar `src/Dockerfile` com `node:24-alpine`, `tini` como entrypoint, `npm ci --omit=dev`, usuário `node`, `EXPOSE 8080` e `CMD ["node", "server.js"]`
- [x] 2.3 Buildar `fabricioveronez/kube-news-aiops:<versão>` e confirmar que o processo não roda como root
- [x] 2.4 Confirmar que `docker stop` encerra o container antes do timeout, sem `SIGKILL`

## 3. Ambiente de desenvolvimento (Compose)

- [x] 3.1 Criar `src/Dockerfile.dev` com `node:24-alpine`, dependências instaladas e `CMD ["node", "--watch", "server.js"]`
- [x] 3.2 Criar `docker-compose.yml` na raiz:
  - serviço `postgres` com `postgres:18-alpine`, `env` com aspas, healthcheck `pg_isready` e volume nomeado em `/var/lib/postgresql`;
  - serviço `app` com build por `src/Dockerfile.dev`, bind mount de `src/`, volume anônimo para `node_modules`, `env` `DB_*`, porta `8080:8080` e `depends_on` com `service_healthy`.

## 4. Validação do Compose

- [x] 4.1 Subir com `docker compose up` e confirmar app em `localhost:8080` conectada ao PG 18 (fecha a pendência de compatibilidade do driver)
- [x] 4.2 Criar e listar uma notícia pela app
- [x] 4.3 Executar `docker compose down` (sem `-v`) e `up`, e confirmar que a notícia persiste
- [x] 4.4 Alterar um arquivo `.js` no host e confirmar o reload sem rebuild. Se falhar no macOS, aplicar o fallback do design e registrar
- [x] 4.5 Registrar a evidência (comando e saída) de cada item do checklist do Compose

## 5. Manifesto Kubernetes

- [x] 5.1 Criar `k8s/kube-news.yaml` com o Namespace dedicado
- [x] 5.2 Adicionar o Deployment do Postgres: 1 réplica, `strategy: Recreate`, `postgres:18-alpine`, `env` inline com aspas, readiness e liveness `pg_isready`, sem volume
- [x] 5.3 Adicionar o Service `ClusterIP` do Postgres na porta 5432
- [x] 5.4 Adicionar o Deployment da app:
  - 2 réplicas, imagem com tag SemVer explícita, `env` `DB_*` inline com aspas;
  - initContainer `pg_isready` em loop contra o Service do banco;
  - readiness `/ready` e liveness `/health` na porta 8080;
  - `resources` (requests e limits) declarados.
- [x] 5.5 Adicionar o Service da app `type: LoadBalancer`, porta 80 → `targetPort` 8080, `nodePort: 30080`
- [x] 5.6 Revisar o manifesto: sem ConfigMap, Secret, Ingress, annotations de provedor, `storageClassName` ou `latest`

## 6. Cluster kind

- [x] 6.1 Criar `k8s/kind-config.yaml` com `extraPortMappings` do `containerPort` 30080 para o `hostPort` 8081
- [x] 6.2 Criar o cluster com `kind create cluster --name kube-news --config k8s/kind-config.yaml`
- [x] 6.3 Carregar a imagem com `kind load docker-image fabricioveronez/kube-news-aiops:<versão> --name kube-news`
- [x] 6.4 Pelo MCP Kubernetes, confirmar que o contexto ativo é `kind-kube-news`
- [x] 6.5 Aplicar `k8s/kube-news.yaml` pelo MCP Kubernetes (nunca `kubectl` direto)

## 7. Validação no kind (sempre pelo MCP Kubernetes)

- [x] 7.1 Confirmar o banco Ready, os pods da app passando por `Init` e o rollout da app em 2/2, sem `ImagePullBackOff` nem `CrashLoopBackOff`
- [x] 7.2 Confirmar a app em `localhost:8081`, criando e listando notícia
- [x] 7.3 Confirmar o balanceamento: `curl` em loop em `/health` mostra o `machine` alternando entre os dois pods
- [x] 7.4 Enviar `PUT /unreadyfor/60` a um pod e confirmar que ele sai dos endpoints do Service e o tráfego segue no outro
- [x] 7.5 Enviar `PUT /unhealth` a um pod e confirmar o restart pelo liveness (contador de restarts aumenta)
- [x] 7.6 Deletar o pod do Postgres, confirmar a perda das notícias, fazer o rollout restart da app pelo MCP e confirmar que ela volta a criar e listar (RT14)
- [x] 7.7 Registrar a evidência (chamada ao MCP ou comando e saída) de cada item do checklist do kind

## 8. Documentação

- [x] 8.1 Criar `docs/adrs/009-validacao-local-kind-nodeport.md`: validação local em kind via `nodePort` fixo no Service LoadBalancer, porta 8081 no host, `kind load` sem push
- [x] 8.2 Referenciar o ADR 009 no ADR 001 (seção de consequências sobre o kind) e na seção de decisões globais do `docs/trd.md`
- [x] 8.3 Atualizar o `README.md` com como subir o Compose e como criar e validar o cluster kind
