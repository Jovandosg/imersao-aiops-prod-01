## Why

O kube-news existe para demonstrar containers e Kubernetes, mas hoje o repositório não tem Dockerfile, Compose nem manifesto: foram removidos no commit `5fd228e`, junto com o código da aplicação. As decisões de como Docker e Kubernetes entram no projeto já estão tomadas (brainstorm `docs/brainstorm-docker-kubernetes.md` e ADRs 001–008). Falta transformá-las em artefatos e provar localmente, com Docker Compose e kind, que funcionam antes de qualquer deploy na DigitalOcean.

## What Changes

- Novo `src/Dockerfile` de produção, Node.js 24, publicado como `fabricioveronez/kube-news-aiops` com tag SemVer imutável, sem `latest` (ADRs 005 e 006).
- Novo `src/Dockerfile.dev` com hot-reload por `node --watch`, sem dependência nova.
- Novo `docker-compose.yml` na raiz com a app (build pelo `Dockerfile.dev`) e o PostgreSQL 18, com volume nomeado em `/var/lib/postgresql`.
- Novo manifesto Kubernetes único em `k8s/kube-news.yaml`, só com APIs core. Ele contém:
  - Deployment da app com 2 réplicas, probes `/ready` e `/health` e `env` inline;
  - Deployment do Postgres 18, 1 réplica, `Recreate`, sem volume, com Service `ClusterIP`;
  - Service da app `type: LoadBalancer` com `nodePort` fixo, para o mesmo arquivo servir à DOKS (via LB) e ao kind (via NodePort).
  - Não há ConfigMap, Secret nem Ingress (ADRs 001–004).
- Nova configuração do kind (`k8s/kind-config.yaml`) com `extraPortMappings` do nodePort para uma porta do host diferente da do Compose.
- Validação local obrigatória por checklist objetivo: o Compose exercita o `Dockerfile.dev`, e o kind exercita o `Dockerfile` de produção e o manifesto. Toda interação com o cluster passa pelo MCP Kubernetes, nunca por `kubectl` direto.
- Novo ADR 009, que registra a validação local em kind via NodePort fixo no Service LoadBalancer. Ele refina o ADR 001 sem substituí-lo.

Esta mudança **não** cria nem restaura o código da aplicação. Ela depende de um contrato da app (porta, rotas, variáveis de ambiente), descrito no design, que a aplicação em `src/` precisa cumprir quando chegar.

## Capabilities

### New Capabilities
- `container-image`: imagem de produção da app, com base, usuário não-root, tratamento de sinal, tag imutável e publicação no Docker Hub.
- `dev-environment`: ambiente de desenvolvimento local com Docker Compose, app com hot-reload e PostgreSQL 18 com volume persistente.
- `kubernetes-manifest`: manifesto agnóstico de provedor, com app, banco, probes e exposição por LoadBalancer com nodePort fixo.
- `local-validation`: validação local com Compose e kind, com cluster kind, carga da imagem sem registry, checklist de comportamento e uso exclusivo do MCP Kubernetes.

### Modified Capabilities
<!-- Nenhuma: não há specs existentes em openspec/specs/. -->

## Impact

- **Arquivos novos:** `src/Dockerfile`, `src/Dockerfile.dev`, `src/.dockerignore`, `docker-compose.yml`, `k8s/kube-news.yaml`, `k8s/kind-config.yaml`, `docs/adrs/009-validacao-local-kind-nodeport.md`.
- **Código da aplicação:** nenhuma alteração. É pré-requisito que `src/` exista e cumpra o contrato do design.
- **Dependências externas:** Docker Hub (registry público), imagens `node:24-alpine` e `postgres:18-alpine`, kind instalado localmente.
- **Operação:** deploy manual pelo MCP Kubernetes (ADR 007). O deploy na DOKS fica fora desta mudança: o done é "validado no Compose e no kind".
- **Documentação:** `docs/trd.md` e ADR 001 ganham referência ao ADR 009.
