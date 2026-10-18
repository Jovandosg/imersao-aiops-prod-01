---
adr_number: "009"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 009: Validação local em kind via NodePort fixo no Service LoadBalancer

## Contexto

O manifesto é único e agnóstico de provedor ([ADR 004](004-manifesto-kubernetes-agnostico.md)) e expõe a app por `Service type: LoadBalancer` ([ADR 001](001-exposicao-via-service-loadbalancer.md)). Antes de qualquer deploy na DOKS, ele precisa ser validado localmente, e o kind não tem cloud controller: o `EXTERNAL-IP` fica `<pending>`.

Um Service `LoadBalancer` também aloca um nodePort, e o LB da DigitalOcean encaminha o tráfego para ele.

## Alternativas Consideradas

- **`nodePort` fixo no próprio Service LoadBalancer** — o mesmo arquivo roda na DOKS (via LB) e no kind (via NodePort). Contra: a porta 30080 precisa estar livre no cluster.
- **`type: NodePort` no kind, com overlay ou segundo arquivo** — o kind deixaria de validar o arquivo exato da DOKS.
- **cloud-provider-kind** — adiciona uma peça local sem ganho didático.
- **port-forward** — fixa num único pod e não valida balanceamento nem readiness.

## Decisão

O Service da app fixa `nodePort: 30080`. O kind mapeia `30080 → 8081` no host (`k8s/kind-config.yaml`), porque o Compose já usa a 8080 e os dois ambientes podem rodar juntos. A imagem entra no cluster por `kind load docker-image`, sem push; a tag SemVer imutável ([ADR 005](005-docker-hub-publico-com-tag-imutavel.md)) mantém o pull policy em `IfNotPresent`. Toda interação com o cluster passa pelo MCP Kubernetes ([ADR 007](007-deploy-manual-via-mcp-kubernetes.md)).

## Consequências

- **Positivas:** o kind valida o arquivo exato que vai para a DOKS. O tráfego passa pelo kube-proxy, então balanceamento e readiness são testáveis.
- **Negativas:** o `EXTERNAL-IP` fica `<pending>` no kind. Usar `latest` quebraria o `kind load`, pois o pull policy viraria `Always`.
- **Neutras / trade-offs aceitos:** o nodePort 30080 fica reservado no cluster. Se estiver ocupado na DOKS, trocar no manifesto e no `kind-config.yaml`.
