---
name: deploy-kubernetes
description: "Leva uma aplicação já containerizada para Kubernetes e PROVA que funciona: gera o manifesto em um único YAML (Namespace, Secret, banco em StatefulSet com volume, ConfigMap, Deployment com initContainer, liveness/readiness, resources e securityContext, Service NodePort), cria cluster kind local com port mapping, carrega a imagem sem registry e valida com checklist objetivo (rollout, balanceamento entre réplicas, funcionais, readiness tirando pod do Service, liveness reiniciando pod, persistência do banco). Use sempre que o usuário disser 'cria o manifesto Kubernetes', 'sobe no Kubernetes/kind', 'quero rodar no cluster', 'cria deployment e service', 'testa as probes', 'leva pro k8s' — mesmo sem citar kind ou YAML. Se ainda não existir imagem Docker validada, use antes a skill containerizar-docker. Não use para pipelines de CI/CD (pipeline-github-actions) nem para Helm charts."
---

# Deploy em Kubernetes (kind local)

O manifesto só está pronto quando **aplicado num cluster de verdade, com as probes provadas falhando e se recuperando e os dados sobrevivendo à morte do pod do banco**. YAML que passa no `--dry-run` não prova nada sobre probes, ordem de subida ou porta exposta.

Pré-requisito: imagem `<app>:local` já validada em Docker (skill `containerizar-docker`). Se não existir, pare e rode aquela skill primeiro — debugar Dockerfile dentro do cluster é muito mais lento.

## Princípios

- **Fale em português do Brasil.**
- **Planeje antes de criar arquivos.** O plano traz a pré-checagem e **lista explicitamente as regras de validação K1–K12** (comando + esperado) — o usuário confere isso antes de aprovar.
- **Não altere código nem dependências da app.** Problemas da app (ex.: não trata SIGTERM) viram "Pontos de atenção" com sugestão.
- **Sucesso só com evidência** — resultado observado por regra.
- **Não comite** sem pedido. Deixe o cluster rodando e diga como remover.

## Defaults deste usuário

Use sem perguntar; pergunte (AskUserQuestion) só se o contexto divergir — por exemplo, cluster em nuvem ou registry obrigatório.

| Decisão | Default |
|---|---|
| Arquivo de manifesto | **um único** `k8s/<app>.yaml`, recursos separados por `---` |
| Exposição | **Service NodePort** com `nodePort: 30000` fixo |
| Cluster | **kind** nomeado `<app>` com `k8s/kind-config.yaml` (extraPortMappings 30000→30000) |
| Imagem | `kind load docker-image <app>:local` (sem registry), `imagePullPolicy: IfNotPresent` |
| Réplicas da app | 2 (para provar balanceamento e readiness) |
| Banco | StatefulSet + Service headless + `volumeClaimTemplates` 1Gi |

## Fluxo

### Fase 1 — Pré-checagem
```bash
docker images <app>:local                 # imagem existe?
kind version; kubectl version --client
kind get clusters                          # cluster já existe?
kubectl config current-context             # contexto pode estar órfão (aponta p/ cluster apagado)
lsof -iTCP:30000 -sTCP:LISTEN              # porta do NodePort livre?
```
Releia o Dockerfile e o compose do projeto: deles saem porta, variáveis, endpoints de health/ready e o banco. Confirme se a imagem tem tini (afeta o tempo de restart — ver armadilhas).

**Pronto quando:** imagem existe, ferramentas ok, porta livre, sabe se vai criar ou reaproveitar cluster.

### Fase 2 — Manifesto
Parta de `assets/k8s-manifest.yaml` e preencha os placeholders. Ordem no arquivo: Namespace → Secret → Service headless do banco → StatefulSet → ConfigMap → Deployment → Service NodePort.

Pontos que não podem faltar:
- **Secret** para credenciais; app lê via `secretKeyRef` (mesma Secret que o banco usa via `envFrom`).
- **ConfigMap** com o resto das variáveis — nomes exatos do código; `DB_HOST` = nome do Service do banco.
- **initContainer** aguardando o banco (`pg_isready` ou equivalente) — apps que caem sem banco entrariam em CrashLoop.
- **livenessProbe** no endpoint de health e **readinessProbe** no de ready; se a app só tem um, use-o nos dois e reporte.
- **resources** (requests/limits) e **securityContext** non-root, `allowPrivilegeEscalation: false`.
- **PGDATA** em subdiretório do volume (o volume monta com `lost+found`).

Copie também `assets/kind-config.yaml` para `k8s/kind-config.yaml`.

**Pronto quando:** `kubectl apply --dry-run=client -f k8s/<app>.yaml` passa.

### Fase 3 — Cluster e imagem
```bash
kind create cluster --name <app> --config k8s/kind-config.yaml
kind load docker-image <app>:local --name <app>
docker exec <app>-control-plane crictl images | grep <app>
```
Falhas comuns de `kind load` estão em `references/armadilhas.md`.

### Fase 4 — Apply e rollout
```bash
kubectl apply -f k8s/<app>.yaml
kubectl -n <ns> rollout status statefulset/<db> --timeout=180s
kubectl -n <ns> rollout status deployment/<app> --timeout=180s
kubectl -n <ns> get pods,svc,pvc
```
Pod travado? `kubectl -n <ns> describe pod <pod>` e `kubectl -n <ns> logs <pod> -c <container>` (inclusive do initContainer).

### Fase 5 — Validação
Siga `references/validacao.md` (regras K1–K12), com `scripts/smoke-test.sh` para HTTP. Item que não se aplica → "N/A — motivo"; item que falha → diagnosticar, corrigir manifesto, reaplicar, revalidar.

### Fase 6 — Relatório
```
## Arquivos criados
- k8s/<app>.yaml — recursos (lista curta)
- k8s/kind-config.yaml — port mapping

## Como recriar
kind create cluster --name <app> --config k8s/kind-config.yaml
kind load docker-image <app>:local --name <app>
kubectl apply -f k8s/<app>.yaml

## Validação
| # | Teste | Resultado |   ← valor observado (hostnames, tempos, contagens, eventos)

## Pontos de atenção
- (releia references/armadilhas.md e inclua o que se aplicou)

Cluster segue rodando em localhost:30000. Remover: kind delete cluster --name <app>
```
