# Brainstorm — Docker e Kubernetes no kube-news

**Lente:** especificação de projeto de desenvolvimento
**Última sessão:** 2026-10-18

## Problema

Definir como Docker e Kubernetes entram no kube-news, uma aplicação de notícias em Node.js + PostgreSQL feita para **demonstrar o uso de containers e Kubernetes**.

O Docker tem dois papéis: ambiente de desenvolvimento local e empacotamento da aplicação. O Kubernetes roda um **único ambiente na cloud (DigitalOcean)**. Esse ambiente é didático e descartável: os dados não importam e falhar faz parte da proposta, porque a aplicação expõe rotas para simular falhas.

O ponto de partida foi "definir o uso de Docker e Kubernetes". A virada da conversa veio quando o ambiente cloud, chamado de "produção", se revelou um **ambiente de desenvolvimento/demonstração**. Isso reclassificou vários riscos (senha em texto puro, HTTP sem TLS, rotas de chaos públicas) como escolhas conscientes de simplicidade e didática.

Ficaram fora deste brainstorm, por decisão do usuário, os documentos de postmortem e o histórico de commits do repositório.

## Requisitos de negócio

- **RN1: demonstrar containers e Kubernetes.** O projeto é didático. A configuração deve ser simples e legível, em vez de reproduzir boas práticas de produção que escondem o mecanismo.
- **RN2: ambiente de desenvolvimento local** com Docker, para desenvolver a aplicação no dia a dia.
- **RN3: ambiente na cloud** acessível pela internet, para demonstração.
- **RN4: demonstrar o comportamento das probes ao vivo.** As rotas `/unhealth` e `/unreadyfor/:seconds` ficam ativas e públicas no ambiente cloud.
- **RN5: portabilidade.** O manifesto Kubernetes não pode depender da DigitalOcean, para poder rodar em outro cluster.
- **RN6: dados descartáveis.** Perder os dados (inclusive o schema) é aceitável no ambiente cloud.

**Fora de escopo, declarado:**
- ambientes de staging ou múltiplos ambientes;
- pipeline de CI/CD e GitOps;
- TLS/HTTPS e domínio próprio;
- backup e persistência do banco no cluster;
- tratamento de credenciais como dado sensível.

## Requisitos técnicos

### Docker

- **RT1: imagem `fabricioveronez/kube-news-aiops` no Docker Hub, pública.** *Serve:* RN3, RN5. Um registry público dispensa credencial de pull, que seria um Secret (ver RT8). O usuário confirmou que o rate limit do Docker Hub não é problema.
- **RT2: tag imutável, sem `latest`.** *Serve:* RN3. Com deploy manual, a tag é o único registro do que está rodando, e o rollback vira trocar a tag. O formato SemVer é inferido; a alternativa considerada foi o SHA do commit (mais rastreável, menos legível em aula).
- **RT3: Node.js 24.** *Serve:* RN1. O usuário começou com Node 22 e mudou para 24 depois da verificação: o 22 está em maintenance LTS com EOL em 30/04/2027, e o 24 é o active LTS, com EOL em 30/04/2028.
- **RT4: dois Dockerfiles, `Dockerfile` (produção) e `Dockerfile.dev` (desenvolvimento, com hot-reload).** *Serve:* RN2, RN3. A primeira inferência foi um único multi-stage, para evitar divergência. O usuário corrigiu para dois arquivos, buscando granularidade para alterar cada um quando preciso e independência entre as construções. Custo aceito: a base comum (versão do Node, instalação de dependências) é duplicada, e o `Dockerfile` de produção não é exercitado no dev, então precisa ser validado antes de cada deploy.
- **RT5: Docker Compose como ambiente de dev (app + Postgres 18).** *Serve:* RN2. Foi preferido a um Kubernetes local (kind + Tilt/Skaffold) porque o loop de código fica mais simples sem cluster.
- **RT6: volume nomeado no Postgres do Compose, montado em `/var/lib/postgresql`.** *Serve:* RN2. No dev, perder os dados de teste a cada restart atrapalha. **Armadilha:** a partir do PG 18, a imagem oficial usa `PGDATA=/var/lib/postgresql/18/docker` e o volume em `/var/lib/postgresql`. Montar no caminho antigo (`/var/lib/postgresql/data`) falha na subida.

### Kubernetes

- **RT7: manifesto só com APIs core.** Sem annotations da DigitalOcean e sem `storageClassName`. *Serve:* RN5. O que é da DO (cluster DOKS, Load Balancer provisionado pelo cloud controller) fica como pré-requisito do cluster, fora do manifesto.
- **RT8: sem ConfigMap e sem Secret. A configuração vai como `env` inline no Deployment da app e no do banco.** *Serve:* RN1. Motivo declarado: simplicidade e didática. Consequências aceitas:
  - a senha fica em texto puro no YAML versionado;
  - a credencial aparece duplicada (app e banco), e mudar uma sem mudar a outra quebra a conexão;
  - qualquer pessoa com leitura de Deployment no cluster vê a senha.
  Ficou registrado que um Secret não é criptografia (é base64). O ganho real dele seria separar permissão (RBAC) e tirar a senha do spec do pod.
- **RT9: aplicação exposta por `Service type: LoadBalancer`, em HTTP, sem Ingress.** *Serve:* RN3, RN5. TLS no Load Balancer da DO exigiria annotation de certificado, e isso quebraria o RT7. Por isso o ambiente fica só em HTTP (inferido).
- **RT10: 2 réplicas da aplicação.** *Serve:* RN4. Permite mostrar o balanceamento e a readiness tirando um pod do Service sem derrubar a app.
- **RT11: Postgres 18 no cluster, sem volume, como `Deployment` de 1 réplica com estratégia `Recreate`.** *Serve:* RN6, RN1. Sem volume, o StatefulSet perde a razão de existir (identidade estável e volume por réplica). O `Recreate` evita dois Postgres vivos ao mesmo tempo durante um update. A forma do workload é inferida: se a intenção didática for mostrar um StatefulSet, ele volta.
- **RT12: Postgres exposto só internamente (ClusterIP), nunca por LoadBalancer.** *Serve:* RN6, RN3. Com senha em texto puro, expor o banco na internet seria grave. Inferido.
- **RT13: deploy manual, sempre pelo MCP Kubernetes, nunca com `kubectl` direto.** *Serve:* RN3. Vem do `CLAUDE.md` do projeto e da decisão de não ter pipeline.
- **RT14: depois de um restart do banco, reiniciar a aplicação.** *Serve:* RN6. Se o ORM cria o schema no boot da aplicação, o Postgres sem volume volta sem tabelas, e a app dá erro até ser reiniciada. O usuário aceitou a perda de dados. O procedimento operacional ("reinicie a app") é inferido.

## Não-funcionais

| Item | Situação |
|---|---|
| Volume e escala | Baixo, de demonstração (Inferido) |
| Tempo de resposta | Sem requisito específico (Inferido) |
| Autenticação e autorização | A aplicação não tem autenticação. As rotas de chaos são públicas (Decidido) |
| Dados sensíveis | Nenhum. A credencial do banco não é tratada como sensível (Decidido) |
| Disponibilidade e tolerância a falha | Tolerante a perda total de dados. 2 réplicas da app, 1 do banco sem persistência (Decidido) |
| Integrações externas | Só o Docker Hub, como registry (Decidido) |
| Onde roda | Dev: Docker Compose local. Cloud: DigitalOcean Kubernetes (DOKS) (Decidido) |
| Quem opera | O próprio autor, manualmente, pelo MCP Kubernetes (Inferido) |
| Restrições declaradas | Manifesto agnóstico, sem Ingress, ConfigMap ou Secret, acesso por LoadBalancer (Decidido) |

## Estados

| Item | Estado | Fonte/Premissa | Data |
|---|---|---|---|
| Ambiente cloud: DOKS, único, didático e descartável | Decidido | Usuário: "Digital Ocean", "só produção", "é um ambiente de desenvolvimento" | 2026-10-18 |
| Manifesto agnóstico (só APIs core) | Decidido | Usuário: "o manifesto deve ser agnóstico" | 2026-10-18 |
| Exposição por `Service LoadBalancer`, sem Ingress | Decidido | Usuário: "o acesso será via loadbalancer" | 2026-10-18 |
| Somente HTTP, sem TLS | Inferido | TLS no LB da DO exige annotation e quebraria o agnóstico. Se estiver errado: aceitar annotation ou levar o TLS para outra camada | 2026-10-18 |
| Sem ConfigMap e sem Secret; `env` inline | Decidido | Usuário: "não quero o uso de ingress configmap ou secrets"; motivo: "simplicidade e didática" | 2026-10-18 |
| Credencial em texto puro, duplicada | Decidido | Consequência aceita do item acima | 2026-10-18 |
| Postgres no cluster | Decidido | Usuário: "dentro de cluster Kubernetes" | 2026-10-18 |
| Banco sem volume no cluster | Decidido | Usuário: "o banco de dados não precisa de volume" | 2026-10-18 |
| Banco como `Deployment` 1 réplica com `Recreate` | Inferido | Sem volume, o StatefulSet não agrega. Se estiver errado: volta o StatefulSet, por motivo didático | 2026-10-18 |
| Banco só em ClusterIP | Inferido | Senha em texto puro + exposição pública seria grave. Se estiver errado: o banco fica aberto na internet | 2026-10-18 |
| Perda de dados aceita | Decidido | Usuário: "aceitar que pode perder dados" | 2026-10-18 |
| Reiniciar a app depois de um restart do banco | Inferido | Schema criado no boot da app. Se estiver errado: vira requisito da app recriar o schema | 2026-10-18 |
| Rotas de chaos ativas e públicas | Decidido | Usuário: "ficam ativas e expostas" | 2026-10-18 |
| Deploy manual, só um ambiente | Decidido | Usuário: "só produção e o manifesto é executado de forma manual" | 2026-10-18 |
| Deploy pelo MCP Kubernetes | Decidido | `CLAUDE.md` do projeto | 2026-10-18 |
| Registry Docker Hub | Decidido | Usuário: "Docker Hub", "não é um problema" | 2026-10-18 |
| Imagem `fabricioveronez/kube-news-aiops` | Decidido | Usuário | 2026-10-18 |
| Tag SemVer imutável, sem `latest` | Inferido | Rastreabilidade e rollback no deploy manual. Se estiver errado: SHA do commit | 2026-10-18 |
| Node.js 24 | Decidido | Usuário: "usar node 24" | 2026-10-18 |
| Node 24 com EOL em 30/04/2028; Node 22 com EOL em 30/04/2027 | Verificado | [endoflife.ai](https://endoflife.ai/article-nodejs-eol.html), [nodejs.org](https://nodejs.org/en/blog/announcements/node-18-eol-support) | 2026-10-18 |
| Postgres 18 | Decidido | Usuário: "usar o postgre 18", depois de recomendação | 2026-10-18 |
| PG 18 é a estável atual; PG 19 em RC, com GA prevista para 19/11/2026 | Verificado | [postgresql.org – 19 RC 1](https://www.postgresql.org/about/news/postgresql-19-rc-1-released-3409/) | 2026-10-18 |
| PG 16 com EOL em 09/11/2028; política de 5 anos (PG 18 até ~11/2030) | Verificado | [endoflife.ai – PG 16](https://endoflife.ai/postgresql/16) | 2026-10-18 |
| PG 18 na imagem oficial: `PGDATA=/var/lib/postgresql/18/docker`, volume em `/var/lib/postgresql` | Verificado | [Docker Hub – postgres](https://hub.docker.com/_/postgres/), [docker-library/postgres #1370](https://github.com/docker-library/postgres/issues/1370) | 2026-10-18 |
| Docker Hub: pull anônimo limitado a 100 a cada 6h por IP | Verificado | [Docker Docs – pull limits](https://docs.docker.com/docker-hub/usage/pulls/) | 2026-10-18 |
| DOKS: StorageClass padrão `do-block-storage`, só RWO | Verificado | [DO – add volumes](https://docs.digitalocean.com/products/kubernetes/how-to/add-volumes/index.html.md) | 2026-10-18 |
| DOKS provisiona LB da DO a partir de `Service LoadBalancer`; ajustes por annotation | Verificado | [DO – add load balancers](https://docs.digitalocean.com/products/kubernetes/how-to/add-load-balancers/index.html.md) | 2026-10-18 |
| ingress-nginx da comunidade aposentado em 03/2026 | Verificado | [kubernetes.io](https://kubernetes.io/blog/2025/11/11/ingress-Nginx-retirement/) | 2026-10-18 |
| 2 réplicas da app | Inferido | Demonstrar balanceamento e readiness | 2026-10-18 |
| Dev com Docker Compose | Inferido | Loop mais simples que um K8s local | 2026-10-18 |
| Dois Dockerfiles: `Dockerfile` e `Dockerfile.dev` | Decidido | Usuário: "granularidade melhor para alterar caso seja preciso e ter mais independência entre as construções" (corrigiu a inferência de multi-stage único) | 2026-10-18 |
| Volume nomeado no Postgres do Compose | Inferido | Não perder dados de teste no dev | 2026-10-18 |
| Compatibilidade Sequelize/`pg` com PG 18 | Em aberto | Sem declaração explícita. Sequelize 6 diz "PostgreSQL ≥ 9.5" ([sequelize.org](https://sequelize.org/releases/)) | 2026-10-18 |
| Conflito com os defaults da skill `deploy-kubernetes` | Em aberto | A skill gera Secret, ConfigMap, StatefulSet com volume, NodePort e kind | 2026-10-18 |

## Alternativas descartadas

| Alternativa | Por que saiu |
|---|---|
| Ingress com ingress-nginx | Usuário não quer Ingress. Além disso, o ingress-nginx da comunidade foi aposentado em 03/2026, sem patches de segurança |
| Gateway API + cert-manager (TLS no cluster) | Recomendada para quando houvesse domínio + TLS. Saiu junto com a decisão de não ter Ingress e de acessar por LoadBalancer |
| Annotations da DO no Service (tamanho do LB, certificado TLS) | Quebrariam o manifesto agnóstico |
| Secret e ConfigMap | Usuário: simplicidade e didática |
| Secret criado fora do manifesto + runbook | Era a direção sugerida antes da decisão de não usar Secret |
| Postgres em StatefulSet com volume | Sem volume, não agrega. Os dados são descartáveis |
| Postgres operator (CloudNativePG) | Backup e failover não são requisito, e o operador é mais uma peça para manter |
| Banco gerenciado (fora do cluster) | Usuário: banco dentro do cluster |
| DOCR (registry privado da DO) | Exige credencial de pull (um Secret no cluster). Usuário escolheu Docker Hub |
| Tag `latest` | Sem rastreabilidade nem rollback no deploy manual |
| Node 22 | EOL em 04/2027. Usuário trocou para Node 24 |
| Postgres 16 | Duas versões atrás. Antecipa a próxima migração |
| Postgres 19 | Ainda em release candidate. Usar RC num projeto didático seria ensinar a coisa errada |
| Kubernetes local (kind + Tilt/Skaffold) como dev | Mais pesado que o Compose para o loop de código |
| Um Dockerfile multi-stage (alvos dev e prod) | Era a inferência inicial. O usuário preferiu dois arquivos para ter independência entre os builds |
| Pipeline CI/CD, GitOps, staging | Usuário: só um ambiente, deploy manual |
| Rotas de chaos desligadas por env var no cluster | Era a direção sugerida. O usuário quer demonstrar as probes ao vivo no cluster |

## Pendências

- **Compatibilidade do Sequelize/`pg` com o PostgreSQL 18.** *Motivo:* nem o Sequelize nem o node-postgres declaram suporte explícito ao 18. Como a conexão usa o protocolo padrão do Postgres, o risco é baixo. *Destrava:* um teste da aplicação contra o PG 18 na implementação.
- **Defaults da skill `deploy-kubernetes` contra as decisões deste brainstorm.** *Motivo:* a skill gera por padrão Secret, ConfigMap, StatefulSet com volume, Service NodePort e cluster kind. *Destrava:* decisão do usuário entre sobrepor os defaults no pedido ou adaptar a skill.
