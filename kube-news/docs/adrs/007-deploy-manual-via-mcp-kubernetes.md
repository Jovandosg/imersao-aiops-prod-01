---
adr_number: "007"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 007: Deploy manual via MCP Kubernetes

## Contexto

Existe um único ambiente cloud (DOKS), sem staging. O usuário declarou que o manifesto é aplicado de forma manual. O `CLAUDE.md` do projeto proíbe `kubectl` direto e exige o MCP Kubernetes para qualquer comunicação com o cluster.

## Alternativas Consideradas

- **Aplicação manual pelo MCP Kubernetes** — simples, sem infraestrutura de entrega, alinhada ao `CLAUDE.md`. Contra: depende de disciplina e de memória da ordem dos passos.
- **Pipeline de CI/CD (ex.: GitHub Actions)** — repetível. Contra: quem aplica passa a ser o pipeline, em tensão com a regra do MCP. É peça extra para um único ambiente didático.
- **GitOps (Argo CD / Flux)** — estado declarativo sincronizado. Contra: mais um controller no cluster, sem requisito que justifique.

## Decisão

O deploy é **manual, sempre pelo MCP Kubernetes**, nunca com `kubectl` direto. Não há pipeline nem GitOps.

## Consequências

- **Positivas:** nenhuma infraestrutura de entrega para manter. Toda interação com o cluster passa por um único canal, auditável na sessão.
- **Negativas:** sem automação. Build, push da imagem, bump da tag ([ADR 005](005-docker-hub-publico-com-tag-imutavel.md)) e apply são passos manuais e sujeitos a esquecimento.
- **Neutras / trade-offs aceitos:** se um pipeline for introduzido no futuro, este ADR e a regra do `CLAUDE.md` precisam ser revisados juntos.
