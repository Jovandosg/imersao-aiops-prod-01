# Armadilhas de Kubernetes/kind (aprendidas na prática)

| Sintoma | Causa | Tratamento |
|---|---|---|
| `kubectl` dá `connection refused` em 127.0.0.1:<porta> | contexto aponta para cluster kind apagado (ex.: `kind-kind` órfão) | `kind get clusters`; criar cluster nomeado; conferir `current-context` |
| NodePort inacessível no macOS/Windows | Docker Desktop roda numa VM; IP do nó não é roteável do host | `extraPortMappings` no `kind-config.yaml` (30000→30000) — precisa existir **na criação** do cluster |
| Conflito de porta com o docker-compose | compose usa a porta da app (ex.: 8080) no host | NodePort 30000 mapeado para host 30000 |
| `kind load` falha (`content digest not found`, manifest list) | imagem com attestation/provenance (BuildKit + containerd store) | `docker build --provenance=false -t <app>:local <dir>` ou `docker save <app>:local -o img.tar && kind load image-archive img.tar --name <cluster>` |
| `ErrImagePull`/`ImagePullBackOff` com imagem local | tag `latest` força pull ou imagem não carregada | tag explícita (`:local`) + `imagePullPolicy: IfNotPresent` + checar K1 |
| Pod da app em CrashLoop no início | app cai sem banco | initContainer com `pg_isready` (ou `nc -z`) |
| Postgres não sobe: "directory not empty" | volume montado contém `lost+found` | `PGDATA` em subdiretório (`/var/lib/postgresql/data/pgdata`) |
| Restart por liveness leva ~60s | ~30s de probe falhando + 30s de `terminationGracePeriod` porque PID 1 ignora SIGTERM | tini no Dockerfile (skill containerizar-docker) ou handler de SIGTERM na app |
| Erros de `ALTER TABLE`/migração em réplicas novas | N réplicas rodando migração/sync no boot ao mesmo tempo | aceitável em lab (o pod reinicia e estabiliza); sugerir Job de migração ou 1 réplica no primeiro deploy |
| `runAsNonRoot` bloqueia o container | imagem roda como root e sem `runAsUser` | `runAsUser: 1000` alinhado ao `USER` do Dockerfile |
| Endpoints de fault-injection (`/unhealth`, `/unreadyfor`) acessíveis por qualquer um | NodePort expõe todas as rotas | ok em laboratório; reportar; em produção bloquear via Ingress/NetworkPolicy |
| Senha em texto puro no YAML | Secret com `stringData` versionado | ok em lab; sugerir Sealed Secrets/External Secrets ou criar o Secret fora do repo |
