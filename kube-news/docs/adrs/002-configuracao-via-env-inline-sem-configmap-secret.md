---
adr_number: "002"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 002: Configuração via env inline, sem ConfigMap e Secret

## Contexto

A aplicação lê a configuração de variáveis de ambiente (`DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSL_REQUIRE`). O Postgres precisa das credenciais equivalentes na própria imagem. O projeto é didático e o ambiente cloud é descartável, sem dado sensível.

O usuário declarou que não quer ConfigMap nem Secret, por **simplicidade e didática**.

## Alternativas Consideradas

- **`env` inline nos Deployments** — tudo visível num único lugar, sem objetos intermediários nem nomes que precisam bater entre si. Contra: senha em texto puro e credencial duplicada.
- **ConfigMap + Secret no manifesto** — separa configuração de credencial e permite RBAC sobre o Secret. Contra: mais objetos e mais referências cruzadas. O Secret não criptografa nada (é base64).
- **Secret criado fora do manifesto + runbook de deploy** — tira a senha do git. Contra: um passo manual a mais e um objeto que o manifesto não descreve.

## Decisão

Toda a configuração vai como **`env` inline** no Deployment da aplicação e no do Postgres. **Não há ConfigMap nem Secret** no manifesto. A credencial do banco não é tratada como sensível neste projeto.

## Consequências

- **Positivas:** manifesto mais curto e legível, com tudo o que a app recebe num único bloco. Isso elimina a classe de erro "referência a ConfigMap/Secret com nome errado".
- **Negativas:**
  - a senha do banco fica em texto puro no YAML versionado e permanece no histórico do git;
  - a credencial aparece duplicada (app e banco), e mudar uma sem a outra quebra a conexão;
  - qualquer pessoa com leitura de Deployment no cluster vê a senha.
- **Neutras / trade-offs aceitos:** a decisão só é aceitável porque o ambiente é descartável e sem dado sensível. Se o projeto ganhar um ambiente com dados reais, este ADR deve ser substituído.
