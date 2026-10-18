# Evidência de validação (2026-10-18)

Imagem: `fabricioveronez/kube-news-aiops:1.0.0` (build local, sem push).

## Imagem de produção
| Item | Resultado | Evidência |
|---|---|---|
| Não roda como root | Aprovado | `docker exec ... id` → `uid=1000(node)`; PID 1 `/sbin/tini -- node server.js` |
| `docker stop` sem SIGKILL | Aprovado | tempo < 1s, exit code 143 (SIGTERM; SIGKILL seria 137) |
| `GET /health` na 8080 | Aprovado | `{"state":"up","machine":"..."}` |

## Compose (`docker compose up`)
| Item | Resultado | Evidência |
|---|---|---|
| Subida sem erro, app só após banco healthy | Aprovado | `Container kube-news-postgres-1 Healthy` antes de `app-1 Starting` |
| Conexão com PG 18 | Aprovado | `PostgreSQL 18.6 on aarch64-unknown-linux-musl`; `sequelize.sync` executou os `ALTER TABLE "Posts"` |
| Criar e listar notícia | Aprovado | `POST /post` → 302; listagem contém a notícia |
| Persistência após `down`/`up` | Aprovado | notícia ainda listada após `docker compose down` (sem `-v`) e `up` |
| Hot-reload | Aprovado (macOS) | edição de `server.js` no host → log `Restarting 'server.js'` sem rebuild; sem necessidade de fallback |

## kind (cluster `kind-kube-news`, tudo pelo MCP Kubernetes)
| Item | Resultado | Evidência |
|---|---|---|
| Contexto ativo | Aprovado | `kubectl_context get` → `kind-kube-news` |
| Rollout 2/2, sem ImagePullBackOff | Aprovado | `deployment "kube-news" successfully rolled out`; evento `Container image ... already present on machine` |
| initContainer | Aprovado | `wait-for-postgres` `Terminated/Completed`, exit 0 |
| Service | Aprovado | `kube-news LoadBalancer 80:30080/TCP EXTERNAL-IP <pending>`; `postgres ClusterIP` |
| App em `localhost:8081` | Aprovado | `POST /post` → 302 e notícia listada |
| Balanceamento | Aprovado | 12 requisições com `Connection: close`: 6 para `...rc68h`, 6 para `...ws9pn` |
| Readiness | Aprovado | `PUT /unreadyfor/60` → pod `ws9pn` 0/1; endpoints só `10.244.0.6:8080`; 8/8 requisições no outro pod; voltou a 1/1 depois |
| Liveness | Aprovado | `PUT /unhealth` → eventos `Liveness probe failed: 500` + `Killing ... will be restarted`; `Restart Count: 1` |
| Restart do banco (RT14) | Aprovado | pod do Postgres deletado e recriado; `rollout restart` da app; notícia antiga: 0 ocorrências; nova notícia criada e listada |
