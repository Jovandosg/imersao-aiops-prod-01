# Relatório de Saúde do Cluster

- **Data:** 2026-10-17 (~17:30 -03)
- **Contexto:** `kind-kind`
- **Coleta:** MCP Kubernetes (get / describe / logs / events)

## Resumo executivo

| Item | Status |
|---|---|
| Nó / control plane | 🟢 Saudável |
| Componentes do sistema (`kube-system`, `local-path-storage`) | 🟢 Saudáveis |
| `kube-news/postgres` | 🟢 Running 1/1 |
| `kube-news/kube-news` | 🔴 **Indisponível** (0/2), `CreateContainerConfigError` |
| `default/nginx` | 🔴 **Indisponível** (0/1), `ImagePullBackOff` |

**Situação geral: 🔴 DEGRADADA.** A infraestrutura do cluster está bem, mas **as duas aplicações de usuário estão fora do ar**. Só o banco de dados está funcionando.

---

## 1. Infraestrutura

### Nó

| Nó | Status | Versão | Runtime | CPU | Memória |
|---|---|---|---|---|---|
| `kind-control-plane` | Ready | v1.36.1 | containerd 2.3.1 | 15 vCPU | ~7,7 GiB |

- Condições: `MemoryPressure=False`, `DiskPressure=False`, `PIDPressure=False`, `Ready=True`.
- Sem taints e agendável.
- Recursos alocados: requests de CPU 1150m (7%), requests de memória 674Mi (8%), limits de memória 1414Mi (17%). Sobra bastante capacidade.
- É um cluster de **nó único**, então não há alta disponibilidade (aceitável para kind/local).

### Componentes do sistema

Todos estão `Running` e sem restarts: `etcd`, `kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`, `kindnet`, `coredns` (2/2) e `local-path-provisioner`.

Os warnings de `kube-system` (readiness do scheduler e do CoreDNS, `FailedScheduling` por taint) aconteceram **só durante o bootstrap** (~7 min atrás), antes de o nó ficar Ready. Não se repetiram e não precisam de ação.

---

## 2. Aplicações

### 2.1 `kube-news` (namespace `kube-news`) 🔴 CRÍTICO

| Recurso | Estado |
|---|---|
| Deployment `kube-news` | 0/2 disponíveis |
| Pods `kube-news-b4bcf6446-2xx2g` / `-g6clq` | `CreateContainerConfigError` |
| InitContainer `wait-postgres` | Completed (o banco responde) |
| Service `kube-news` | NodePort `80:30000`, **sem endpoints** |

**Causa raiz:** o container principal não é criado porque referencia um Secret que não existe:

```
Error: secret "postgres" not found
```

Em `k8s/kube-news.yaml:127-131`, a variável `DB_USERNAME` aponta para o Secret **`postgres`**, mas o Secret que existe no namespace se chama **`postgres-secret`**. O `DB_PASSWORD` (linhas 132-136) já usa o nome certo. O `postgres-secret` tem as chaves `POSTGRES_DB`, `POSTGRES_PASSWORD` e `POSTGRES_USER`, então só o nome está errado.

```yaml
# k8s/kube-news.yaml (atual: errado)
- name: DB_USERNAME
  valueFrom:
    secretKeyRef:
      name: postgres          # ← não existe
      key: POSTGRES_USER
```

**Correção:** trocar `name: postgres` por `name: postgres-secret` e reaplicar o manifesto. Não é preciso mexer no banco: o pod se recupera sozinho quando a referência fica válida.

**Impacto:** a aplicação está totalmente indisponível. A porta 30000 não responde porque o Service não tem nenhum pod pronto.

### 2.2 `postgres` (namespace `kube-news`) 🟢 OK

| Recurso | Estado |
|---|---|
| StatefulSet `postgres` | 1/1, `postgres-0` Running, 0 restarts |
| PVC `data-postgres-0` | Bound, 1Gi, RWO, storageClass `standard` |
| Service `postgres` | Headless (ClusterIP None), 5432 |

Os logs mostram a inicialização concluída e `database system is ready to accept connections`. O initContainer da aplicação confirmou que o banco está acessível (`pg_isready` ok).

### 2.3 `nginx` (namespace `default`) 🔴 CRÍTICO

| Recurso | Estado |
|---|---|
| Deployment `nginx` | 0/1 disponíveis |
| Pod `nginx-859bbb7d4b-2w5r8` | `ImagePullBackOff` (20+ tentativas em ~6 min) |

**Causa raiz:** erro de digitação no nome da imagem e do container: aparece **`ngin`** onde deveria ser **`nginx`**.

```
Failed to pull image "ngin": ... docker.io/library/ngin:latest: pull access denied, repository does not exist
```

**Outros problemas do deployment:**
- Não fixa a versão da imagem (usaria `:latest` de forma implícita).
- Não tem `resources` (QoS `BestEffort`) nem probes.
- Está no namespace `default`.

**Correção:** ajustar a imagem para `nginx:<versão fixa>`, por exemplo `nginx:1.27-alpine`. Se este deployment não fizer parte do projeto (não existe manifesto dele no repositório), vale confirmar se ele deveria mesmo existir ou se pode ser removido.

---

## 3. Observações de boas práticas

| Tema | `kube-news` | `postgres` | `nginx` |
|---|---|---|---|
| Requests/limits | ✅ 50m-250m / 64-256Mi | ✅ 100m-500m / 256-512Mi | ❌ ausente |
| Liveness/Readiness | ✅ `/health` e `/ready` | — | ❌ ausente |
| Tag de imagem fixa | ⚠️ `:local` (ok para kind) | ✅ `16-alpine` | ❌ sem tag |
| Persistência | n/a | ✅ PVC | n/a |
| Réplicas | 2 | 1 | 1 |

- `kube-news`: o timeout das probes é de 1s e a readiness tem `failureThreshold=1`. Isso é sensível, e uma resposta lenta isolada já tira o pod do Service. Vale considerar `failureThreshold: 2-3`.
- Os pods usam o ServiceAccount `default`. Pode ser útil desabilitar `automountServiceAccountToken` nas aplicações que não usam a API do Kubernetes.

---

## 4. Ações recomendadas (por prioridade)

1. **[P1]** `k8s/kube-news.yaml:130`: trocar `name: postgres` por `name: postgres-secret` e reaplicar. Isso restaura o kube-news.
2. **[P1]** `default/nginx`: corrigir a imagem `ngin` para `nginx:<tag>`, ou remover o deployment se ele não for intencional.
3. **[P2]** `nginx`: adicionar resources e probes.
4. **[P3]** `kube-news`: deixar a readiness probe mais tolerante (`failureThreshold`).

Depois das correções, validar com: rollout do deployment `kube-news` concluído (2/2), endpoints no Service `kube-news` e HTTP 200 em `localhost:30000`.

---

## 5. Correções aplicadas (2026-10-17)

**Status atual: 🟢 SAUDÁVEL.** Todos os pods estão `Running` e prontos, sem restarts.

### Alterações

| # | Onde | Alteração |
|---|---|---|
| 1 | `k8s/kube-news.yaml` (Deployment) | `DB_USERNAME` agora usa o Secret `postgres-secret` em vez de `postgres` |
| 2 | `k8s/kube-news.yaml` (StatefulSet) | **Achado novo:** o `mountPath` era `/var/lib/postgresql/dat`, mas o `PGDATA` aponta para `/var/lib/postgresql/data/pgdata`. Os dados ficavam fora do PVC e se perderiam a cada restart. Corrigido para `/var/lib/postgresql/data` |
| 3 | `k8s/kube-news.yaml` (ConfigMap) | **Achado novo:** `DB_DATABASE: vaidarruim` não batia com o `POSTGRES_DB` (`kubedevnews`). Corrigido para `kubedevnews` |
| 4 | `k8s/kube-news.yaml` (Deployment) | `failureThreshold` da readiness passou de 1 para 3 |
| 5 | `default/nginx` (patch no cluster) | Imagem e container renomeados de `ngin` para `nginx:1.27-alpine`. Adicionados resources (25m-200m / 32-128Mi) e probes HTTP em `/` |

### Validação

| Verificação | Resultado |
|---|---|
| Rollout `kube-news` (2/2), `postgres` (1/1), `nginx` (1/1) | ✅ |
| EndpointSlice `kube-news` com 2 IPs | ✅ |
| `GET /`, `/health`, `/ready` em `localhost:30000` | ✅ 200 |
| Conexão com o banco (logs com sync do Sequelize no `kubedevnews`) | ✅ |
| Criação de post via `POST /post` | ✅ 302 e post listado |
| Persistência: post continua listado depois de `rollout restart` do postgres | ✅ |
| nginx serve a página padrão (`wget` dentro do pod) | ✅ |

### Pendências

- O `nginx` não tem manifesto no repositório. A correção foi feita só no cluster e se perde se o cluster for recriado.
- Nesta etapa, o `nginx` não ganhou um Service.
