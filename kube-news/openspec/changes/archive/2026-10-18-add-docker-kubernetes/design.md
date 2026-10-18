## Context

O kube-news é uma aplicação de notícias em Node.js + PostgreSQL, didática, feita para demonstrar containers e Kubernetes. O brainstorm (`docs/brainstorm-docker-kubernetes.md`) e os ADRs 001–008 já fixam as decisões de alto nível. Esta mudança as materializa e acrescenta uma decisão nova: a validação local.

Estado atual: o repositório só tem documentação. O commit `5fd228e` removeu `src/`, `docker-compose.yml` e `k8s/`, e por decisão do usuário eles **não** serão restaurados do histórico. A infra é escrita contra o contrato da app descrito abaixo.

Restrições:
- `CLAUDE.md`: nunca usar `kubectl` direto. Todo acesso ao cluster passa pelo MCP Kubernetes.
- ADR 004: manifesto só com APIs core, sem dependência da DigitalOcean.
- ADR 002: sem ConfigMap e sem Secret. A senha em texto puro é aceita.

### Contrato da aplicação (premissa)

A infra assume que a aplicação em `src/` cumpre o contrato abaixo. Se ele mudar, os artefatos desta mudança mudam junto.

| Item | Valor esperado |
|---|---|
| Runtime / entrada | Node.js 24, `package.json` + `package-lock.json` em `src/`, iniciada por `node server.js` |
| Porta | 8080 |
| Liveness | `GET /health` → 200 saudável, 500 após `PUT /unhealth`. Corpo JSON com `machine` = hostname |
| Readiness | `GET /ready` → 200 pronto, 500 durante `PUT /unreadyfor/:seconds` |
| Configuração | `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_SSL_REQUIRE` |
| Schema | criado pela app no boot (ex.: `sequelize.sync`) |
| Estáticos | `static/` servido pela app, views renderizadas no servidor |

**Conferência do contrato (task 1.2):** `src/` cumpre o contrato, sem divergências que mudem a infra. Observações:
- `healthMid` roda antes de todas as rotas: após `PUT /unhealth`, todas as rotas (inclusive `/ready`) respondem 500.
- `initDatabase()` não é aguardado (`seque.sync` sem `await`/`catch`): com o banco fora do ar, o boot gera rejeição não tratada e o processo cai. Reforça o D6 (initContainer) e o `depends_on: service_healthy` do Compose.
- `package.json` não declara `engines`; a versão da app é `1.0.0` (usada como tag inicial da imagem).

## Goals / Non-Goals

**Goals:**
- `Dockerfile` de produção e `Dockerfile.dev` independentes, ambos Node 24 (ADR 006).
- Compose de dev com PG 18 e volume no caminho correto do PG 18.
- Manifesto único que roda sem alteração no kind e na DOKS.
- Validação local por checklist objetivo, no Compose e no kind, antes de qualquer deploy cloud.

**Non-Goals:**
- Criar, restaurar ou alterar o código da aplicação.
- Deploy na DOKS (vem depois, já com o manifesto validado).
- CI/CD, GitOps, staging, TLS, domínio, Ingress, ConfigMap, Secret, persistência do banco no cluster.
- Readiness que verifique o banco ou recriação automática do schema (RT14 continua procedimento manual).

## Decisions

### D1. Service LoadBalancer com `nodePort: 30080` fixo, testado no kind por NodePort
Um Service `LoadBalancer` também aloca um nodePort, e o LB da DO encaminha para ele. Fixar o nodePort deixa o kind acessar a app pelo caminho NodePort enquanto o `EXTERNAL-IP` fica `<pending>`, com o **mesmo arquivo** que vai para a DOKS.
- *Alternativa:* `type: NodePort` literal no kind, com overlay kustomize ou um segundo arquivo. Descartada porque o kind deixaria de validar o arquivo exato da DOKS, e o projeto ganharia estrutura sem ganho didático.
- *Alternativa:* cloud-provider-kind. Descartada por decisão do usuário: o teste local é por NodePort.
- *Alternativa:* port-forward pelo MCP. Descartada porque fixa num único pod e não valida balanceamento nem readiness.
- O tráfego NodePort passa pelo kube-proxy, então balanceamento e readiness continuam testáveis.
- Esta decisão vira o ADR 009.

### D2. kind mapeia `30080 → 8081` no host
O Compose já usa `8080` no host. Mapear o kind para `8081` deixa os dois ambientes rodarem juntos, o que permite comparar dev e "prod local" lado a lado.

### D3. Imagem no kind por `kind load`, sem push
A tag SemVer imutável (ADR 005) faz o pull policy padrão ser `IfNotPresent`, e a imagem carregada no node é usada sem tocar o Docker Hub. O manifesto não precisa de `imagePullPolicy` especial. O fluxo fica: build → `kind load` → apply → validar → (depois) push → DOKS.
- Usar `latest` quebraria isso, porque o pull policy viraria `Always`. Mais um motivo para o ADR 005.

### D4. Imagem de produção: `node:24-alpine` + `tini` + usuário `node`
Alpine para uma imagem pequena. O `tini` como PID 1 repassa sinais e colhe zumbis, então o `SIGTERM` do kubelet chega ao Node. O usuário `node`, que já existe na imagem oficial, evita rodar como root. A instalação usa `npm ci --omit=dev` com `package*.json` copiados antes do código, para aproveitar o cache de camadas.
- *Alternativa:* multi-stage. Desnecessário para JS puro sem build step. Pode ser revisto se a app ganhar etapa de build.

### D5. Hot-reload com `node --watch`
O watch nativo do Node 24 evita adicionar `nodemon` ao `package.json`, o que respeita a regra de não mexer na app. No Compose, o código é montado como bind mount, e `node_modules` fica num volume anônimo para não ser sobrescrito pelo bind.
- *Risco:* bind mounts no Docker Desktop do macOS podem não propagar eventos de arquivo de forma confiável. Ver Riscos.

### D6. initContainer `pg_isready` na app
O boot da app conecta ao banco para criar o schema. Sem esperar o banco, ela pode falhar e entrar em CrashLoop até ele subir. Um initContainer com a mesma imagem `postgres:18-alpine` e `pg_isready -h <svc-banco>` em loop deixa a ordem explícita e visível em aula (pod em `Init:0/1`).
- *Alternativa:* aceitar o CrashLoop como comportamento "natural". Descartada porque polui a demonstração das probes com restarts que não vêm delas.
- O initContainer não cobre o restart do banco com a app já rodando (RT14). Esse caso continua sendo procedimento manual: `rollout restart` da app pelo MCP.

### D7. Postgres como Deployment `Recreate`, sem volume, só ClusterIP
Segue o ADR 003. Sem volume, o StatefulSet não agrega nada. O `Recreate` evita dois Postgres vivos. As probes usam `pg_isready` via `exec`. O PG 18 sem volume grava na camada do container, e o `VOLUME` declarado na imagem é ignorado pelo Kubernetes.

### D8. Configuração por `env` inline, com aspas
Segue o ADR 002. Os valores `DB_*` da app e `POSTGRES_*` do banco são repetidos nos dois Deployments, e todo valor vai entre aspas. A senha com `#` só funciona sem aspas por acaso, e num manifesto didático isso não pode ser ensinado.

### D9. Validação por checklist com evidência
"Validado" quer dizer que cada item dos checklists de `specs/local-validation` foi executado com evidência (comando ou chamada ao MCP, mais a saída). Para o balanceamento, usar `curl` em loop: o navegador reusa a conexão (keep-alive) e parece grudar num pod.

### D10. Uso das skills `containerizar-docker` e `deploy-kubernetes`
Se as skills forem usadas na implementação, os defaults delas são **sobrepostos** por este design: dois Dockerfiles (não um), `env` inline (não Secret ou ConfigMap), Postgres em Deployment sem volume (não StatefulSet), Service LB com nodePort fixo (não NodePort puro), PG 18 em `/var/lib/postgresql`, acesso ao cluster só pelo MCP.

## Risks / Trade-offs

- **[`src/` não existe]** → Nenhuma validação roda sem a app. A task 1 confere o contrato e bloqueia o resto se ele não for cumprido.
- **[Contrato diferente do assumido]** (porta, rotas, nome do entrypoint) → A task 1 compara item a item. Divergências ajustam a infra, e o design é atualizado.
- **[Compatibilidade do driver com PG 18]** (pendência do brainstorm) → O checklist do Compose prova a conexão. Se falhar, a correção é na app (versão do `pg`) e fica fora desta mudança.
- **[`node --watch` sem eventos de arquivo no macOS]** → Validar no checklist. Se falhar, as opções são `--watch-path` explícito ou, por último, polling, registrado no design.
- **[nodePort 30080 ocupado na DOKS]** → Baixo risco num cluster dedicado. Se acontecer, trocar a porta no manifesto e no `kind-config`.
- **[Apply no contexto errado]** (o mesmo MCP enxerga kind e DOKS) → Conferir o contexto pelo MCP antes de todo apply (requisito em `local-validation`).
- **[Paridade parcial]** → No Compose, o banco tem volume e a app roda o `Dockerfile.dev`. No kind, não há volume e a imagem é a de produção. É intencional: cada ambiente valida a metade que o outro não cobre.
- **[Senha em texto puro no git]** → Aceito pelo ADR 002, já que o ambiente é descartável.

## Migration Plan

Não há estado anterior em execução. A ordem de entrega é:
1. Conferir o contrato da app em `src/`.
2. Dockerfiles → Compose → checklist do Compose.
3. Manifesto + `kind-config` → cluster kind → `kind load` → apply pelo MCP → checklist do kind.
4. ADR 009 e referências no TRD e no ADR 001.

Rollback local: `docker compose down -v` e `kind delete cluster --name kube-news`.

## Open Questions

- Origem do código da app: quem entrega `src/` e quando? Até lá, as tasks a partir do grupo 2 ficam bloqueadas.
- Versão inicial da imagem: `1.0.0`, ou a versão do `package.json` da app quando ela chegar?
- O uso do CLI `kind` (`create cluster`, `load docker-image`, `delete cluster`) via shell é permitido pelo `CLAUDE.md`? Premissa: sim, porque não é `kubectl` e não fala com a API do cluster além do bootstrap.
