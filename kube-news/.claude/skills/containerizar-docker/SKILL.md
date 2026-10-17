---
name: containerizar-docker
description: "Containeriza uma aplicação de ponta a ponta — descobre no código o que importa (stack, porta, entrypoint, paths relativos, variáveis de ambiente, banco, endpoints de health/ready/metrics), cria Dockerfile e .dockerignore no diretório da app, docker-compose com o banco na raiz, sobe tudo e VALIDA com checklist objetivo (health, readiness, CRUD, estáticos, métricas, banco, fault-injection, persistência, tempo de shutdown) antes de declarar pronto. Funciona para Node.js, Python, Go e Java. Use sempre que o usuário disser 'cria o Dockerfile', 'dockeriza/containeriza a aplicação', 'quero rodar isso no Docker', 'monta o docker compose', 'sobe a app com o banco local', 'valida se roda em container', ou quando o objetivo final for Kubernetes e ainda não existir imagem — mesmo sem citar Docker. Não use para manifestos Kubernetes/cluster (use deploy-kubernetes) nem para pipelines de CI (use pipeline-github-actions)."
---

# Containerizar com Docker

Uma app só está containerizada quando **a imagem sobe, conversa com o banco e passa no checklist de validação com saída real**. Escrever o Dockerfile é a parte pequena; a parte que evita retrabalho é descobrir antes como a app se comporta (de onde lê arquivos, o que faz se o banco não estiver pronto, se trata SIGTERM) e provar depois que tudo funciona.

Esta skill é o primeiro passo do caminho até Kubernetes. Quando terminar, o próximo é a skill `deploy-kubernetes`.

## Princípios

- **Fale em português do Brasil** em explicações, planos e relatórios.
- **Planeje antes de criar arquivos.** O plano mostra o que será criado e onde **e lista explicitamente as regras de validação D1–D13** (comando + esperado) — o usuário confere isso antes de aprovar.
- **Não altere código nem dependências da aplicação sem pedir.** Containerizar é empacotar o que existe. Versões antigas ou vulneráveis podem ser intencionais (projetos didáticos de DevSecOps fazem isso de propósito) — aponte, não corrija.
- **Sucesso só com evidência.** Cada item de validação é reportado com o resultado que saiu do comando, não com o que se espera.
- **Não comite** sem pedido explícito. Ao final, deixe o ambiente rodando e diga como derrubar.

## Defaults deste usuário

Use sem perguntar; pergunte só se o projeto tornar o default impossível.

| Decisão | Default |
|---|---|
| Local do Dockerfile | **dentro do diretório da app** (ex.: `src/Dockerfile`); o contexto de build é esse diretório |
| `.dockerignore` | ao lado do Dockerfile |
| docker-compose | na raiz do repo, `build: ./<dir-app>` |
| Nome da imagem | `<app>:local` |
| Banco | imagem oficial alpine (ex.: `postgres:16-alpine`) com volume nomeado |

## Fluxo

### Fase 1 — Descoberta
Leia `references/descoberta.md` e levante cada item lá listado. O que mais causa retrabalho:
- **Paths relativos ao diretório corrente** (`express.static('static')`, `views/`, `templates/`) → o `WORKDIR` precisa conter o conteúdo do diretório da app, não o repo.
- **Init que depende do banco** (ex.: `sequelize.sync()` sem await, migração no boot) → a app cai se subir antes do banco.
- **Porta real** (às vezes fixa no código, diferente do README ou de arquivos de exemplo).
- **Variáveis de ambiente e defaults** — copie os nomes exatos do código.

Cheque também o ambiente: `docker version`, `docker compose version`, portas livres (`lsof -iTCP:<porta> -sTCP:LISTEN`).

**Pronto quando:** você consegue preencher a tabela de descoberta sem "não sei".

### Fase 2 — Dockerfile e .dockerignore
Use o template da stack em `references/dockerfiles.md`. Requisitos que valem para todas:
- imagem base slim/alpine numa versão **LTS ativa** (confira a data de hoje vs. ciclo de vida);
- dependências copiadas e instaladas **antes** do código (cache de camada);
- só dependências de produção; lockfile respeitado (`npm ci`, `pip install -r`, `go mod download`);
- **usuário não-root**;
- **tini como ENTRYPOINT** — sem um init, o processo da app vira PID 1, ignora SIGTERM e cada stop/restart espera o timeout inteiro (10s no Docker, 30s no Kubernetes). Foi isso que fez um restart por liveness levar ~58s;
- `EXPOSE` da porta real.

**Pronto quando:** `docker build` passa.

### Fase 3 — docker-compose
Parta de `assets/docker-compose.yml`. O essencial: banco com `healthcheck` e volume; app com `depends_on: condition: service_healthy` e as variáveis da descoberta apontando para o nome do serviço do banco.

**Pronto quando:** `docker compose config` valida sem erro.

### Fase 4 — Validação
Siga `references/validacao.md` (regras D1–D13) e use `scripts/smoke-test.sh` para as checagens HTTP. Regra de ouro: item que não se aplica vira **"N/A — motivo"**, nunca some do relatório. Item que falha → leia logs, corrija, revalide.

**Pronto quando:** todos os itens estão ✅ ou N/A justificado.

### Fase 5 — Relatório
Sempre neste formato:

```
## Arquivos criados
- caminho — o que é (1 linha)

## Como executar
<comandos>

## Validação
| # | Teste | Resultado |   ← resultado real, com valor observado

## Pontos de atenção
- riscos encontrados (senha em texto puro, deps vulneráveis, porta divergente em arquivo de exemplo…)

## Próximo passo
Kubernetes → skill deploy-kubernetes. Ambiente segue rodando; derrubar com `docker compose down` (`-v` apaga dados).
```

Antes de escrever o relatório, releia `references/armadilhas.md` — se algo de lá aconteceu e não foi tratado, entra em "Pontos de atenção".
