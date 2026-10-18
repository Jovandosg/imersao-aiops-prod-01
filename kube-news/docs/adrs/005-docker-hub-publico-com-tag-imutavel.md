---
adr_number: "005"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 005: Docker Hub público com tag imutável

## Contexto

O cluster precisa baixar a imagem da aplicação de um registry. Como não há Secret no manifesto ([ADR 002](002-configuracao-via-env-inline-sem-configmap-secret.md)), um registry privado exigiria uma credencial de pull, que é justamente um Secret. O deploy é manual ([ADR 007](007-deploy-manual-via-mcp-kubernetes.md)), então a tag da imagem é o único registro de qual versão está rodando.

Fato verificado em 2026-10-18: o Docker Hub limita o pull anônimo a 100 a cada 6h por IP ([Docker Docs](https://docs.docker.com/docker-hub/usage/pulls/)). O usuário confirmou que isso não é problema para este projeto.

## Alternativas Consideradas

- **Docker Hub público** — não exige credencial de pull. Contra: imagem pública e rate limit anônimo.
- **DOCR (registry da DigitalOcean)** — integrado ao DOKS. Contra: a integração cria um Secret de pull no cluster, e o registry fica amarrado ao provedor.
- **GHCR público** — mesmas vantagens do Docker Hub. Não foi escolhido.
- **Tag `latest`** — cômoda. Contra: sem rastreabilidade nem rollback, e força `imagePullPolicy: Always`.
- **Tag por SHA do commit** — mais rastreável. Contra: menos legível em aula.

## Decisão

A imagem é publicada no **Docker Hub, pública, como `fabricioveronez/kube-news-aiops`**, com **tag imutável em SemVer (`1.0.0`, `1.0.1`...), nunca `latest`** *(premissa — confirme ou corrija: o formato SemVer foi inferido)*.

## Consequências

- **Positivas:** nenhuma credencial de pull no cluster. O manifesto continua sem Secret e agnóstico. O rollback é trocar a tag no manifesto.
- **Negativas:** a imagem é pública: qualquer pessoa pode baixá-la, e ela não pode conter nada sensível. O bump da tag a cada deploy é disciplina manual.
- **Neutras / trade-offs aceitos:** o rate limit anônimo só pesaria com muitos nós ou recriações em sequência. A imagem `postgres:18` também vem do Docker Hub.
