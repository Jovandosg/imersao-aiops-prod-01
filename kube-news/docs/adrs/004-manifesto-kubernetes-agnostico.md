---
adr_number: "004"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 004: Manifesto Kubernetes agnóstico de provedor

## Contexto

O ambiente cloud é a DigitalOcean (DOKS), mas o usuário declarou que o manifesto deve ser agnóstico: ele precisa rodar em outro cluster sem reescrita. Os pontos em que um manifesto costuma se amarrar ao provedor são: annotations de Load Balancer, `storageClassName`, registry privado com credencial de pull e controllers de Ingress específicos.

## Alternativas Consideradas

- **Manifesto só com APIs core; o que é do provedor vira pré-requisito do cluster** — portável e simples. Contra: abre mão de recursos do provedor (TLS no LB, tamanho do LB).
- **Kustomize com base agnóstica + overlay por provedor** — portável e com acesso aos recursos do provedor. Contra: mais uma ferramenta e mais arquivos, para um único ambiente.
- **Manifesto específico da DO** — acesso total aos recursos do provedor. Contra: viola o requisito.

## Decisão

O manifesto usa **só APIs core do Kubernetes**, sem annotations da DigitalOcean, sem `storageClassName` e sem referência a recursos do provedor. Tudo o que é da DO fica fora do manifesto, como **pré-requisito do cluster**: o próprio cluster DOKS e o Load Balancer, provisionado pelo cloud controller a partir de `Service type: LoadBalancer`.

## Consequências

- **Positivas:** o mesmo arquivo aplica em DOKS, em outra cloud ou num cluster local. Isso reforça as escolhas de LoadBalancer sem annotation ([ADR 001](001-exposicao-via-service-loadbalancer.md)), banco sem volume ([ADR 003](003-postgres-no-cluster-sem-persistencia.md)) e registry público ([ADR 005](005-docker-hub-publico-com-tag-imutavel.md)).
- **Negativas:** sem TLS no LB e sem ajuste fino do LB da DO.
- **Neutras / trade-offs aceitos:** em clusters sem cloud controller (ex.: kind), o `Service LoadBalancer` não recebe IP externo sem um provedor de LB local. A portabilidade é do manifesto, não do modo de acesso.
