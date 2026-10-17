# Validação Kubernetes — regras K1–K12

Cada regra tem **comando + resultado esperado**. O relatório traz uma linha por regra com o valor **observado** (hostnames, tempos, contagens, eventos).

- Não se aplica? → `N/A — motivo` (ex.: "app sem endpoint de fault-injection; readiness testada de outro jeito"). Nunca omita.
- Falhou? → `describe pod`, `logs` (inclusive `-c <initContainer>`), `get events --sort-by=.lastTimestamp`; corrija o manifesto, reaplique, revalide.

Defina: `NS=<ns>`, `U=localhost:30000`, `S=<dir-da-skill>/scripts/smoke-test.sh`.

| # | Regra | Como | Esperado |
|---|---|---|---|
| K1 | Imagem no nó | `docker exec <cluster>-control-plane crictl images \| grep <app>` | `<app>:local` presente |
| K2 | Contexto | `kubectl config current-context` | `kind-<cluster>` |
| K3 | Apply + rollout | `kubectl apply -f k8s/<app>.yaml`; `rollout status` do StatefulSet e do Deployment | todos `Running`/`Ready`, 0 restarts |
| K4 | Volume | `kubectl -n $NS get pvc` | `Bound` |
| K5 | Service | `kubectl -n $NS get svc <app>` | `NodePort 80:30000/TCP` |
| K6 | Balanceamento | `REPEAT=10 bash $S $U` | respostas de `/health` distribuídas entre as 2 réplicas (hostname = nome do pod) |
| K7 | Funcionais | regras D3–D9 da skill containerizar-docker contra `$U` | mesmos resultados do Docker |
| K8 | Banco | `kubectl -n $NS exec postgres-0 -- psql -U <user> -tAc 'select count(*) from "<tabela>";'` | contagem bate com o inserido |
| K9 | Readiness | `kubectl -n $NS port-forward pod/<pod> 18080:<porta> &` → fault-injection de ready (ex.: `curl -X PUT localhost:18080/unreadyfor/30`) → `get pods`, EndpointSlice e `REPEAT=6` no NodePort | pod `0/1`, `ready=false` no EndpointSlice, tráfego só no outro pod; volta `Ready` depois de ~N s |
| K10 | Liveness | fault-injection de health (ex.: `curl -X PUT localhost:18080/unhealth`) → poll de `restartCount` → `wait --for=condition=Ready` → `get events --field-selector involvedObject.name=<pod>` | evento `failed liveness probe, will be restarted`; `restartCount` +1; pod volta `Ready`. **Meça o tempo**: ~30s (3×10s de probe) + shutdown; se passar de ~40s, a imagem não trata SIGTERM (sem tini) |
| K11 | Persistência | `kubectl -n $NS delete pod postgres-0` → `wait --for=condition=Ready pod/postgres-0` → repetir K8 e uma leitura da app | mesma contagem; app continua servindo |
| K12 | Logs | `kubectl -n $NS logs deploy/<app> \| grep -iE 'error\|exception'` | sem erros de conexão/migração (registrar se houver corrida de migração entre réplicas) |

EndpointSlice legível:
```bash
kubectl -n $NS get endpointslice -l kubernetes.io/service-name=<app> \
  -o jsonpath='{range .items[*].endpoints[*]}{.targetRef.name}={.conditions.ready}{"\n"}{end}'
```

Sem fault-injection na app: para K9, aponte temporariamente a readinessProbe para um path inexistente num `kubectl patch` e observe o pod sair do Service; para K10, `kubectl exec <pod> -- kill 1` mostra o restart (não testa a probe em si — reporte isso). Desfaça o patch ao final.

Encerre o `port-forward` (`kill %1` ou PID) antes do relatório.
