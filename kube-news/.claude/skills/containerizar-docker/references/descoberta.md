# Descoberta — o que levantar antes de escrever qualquer arquivo

Preencha esta tabela lendo o código (não só o README — ele pode estar desatualizado). Ela alimenta o Dockerfile, o compose e, depois, o manifesto Kubernetes.

| Item | Onde procurar | Por que importa |
|---|---|---|
| Stack e versão | `package.json` (`engines`), `pyproject.toml`/`requirements.txt`, `go.mod`, `pom.xml`/`build.gradle`, `.nvmrc`, `.python-version` | escolhe a imagem base; sem versão declarada, use a LTS ativa e diga isso no relatório |
| Diretório da app | onde está o manifesto de deps (`src/`, raiz, `app/`) | é onde vai o Dockerfile e o contexto de build |
| Entrypoint | `scripts.start`, `main`, `if __name__`, `cmd/`, `Main-Class` | o `CMD` do container |
| Porta | `listen(`, `PORT`, `server.port`, `uvicorn --port` | `EXPOSE`, mapeamento no compose, `containerPort` no K8s. Verifique se é fixa no código ou vem de env |
| Paths relativos ao cwd | `express.static(`, `views`, `templates`, `open('./…')`, `static_folder` | o `WORKDIR` precisa ser o diretório que contém essas pastas |
| Variáveis de ambiente | `process.env.`, `os.environ`, `os.Getenv`, `@Value`, `.env.example` | nomes **exatos** + defaults; defaults sensíveis (senha fixa) vão para "Pontos de atenção" |
| Dependências externas | drivers (`pg`, `mysql2`, `psycopg`, `redis`, `amqplib`), ORMs | serviços do compose |
| Comportamento no boot | `sync(`, `migrate`, `createAll`, conexão sem retry | se a app cai sem banco → `depends_on: service_healthy` (e initContainer no K8s) |
| Health / readiness | rotas `/health`, `/healthz`, `/ready`, `/actuator/health` | validação agora e probes no K8s depois |
| Métricas | `/metrics`, `prom-client`, `micrometer`, `prometheus_client` | validação |
| Fault-injection | rotas que alteram o estado de health/ready (ex.: `PUT /unhealth`, `PUT /unreadyfor/:s`) | permitem testar probes; são um risco se expostas publicamente |
| Sinais | handlers de `SIGTERM`/`process.on('SIGTERM')`, `server.close()` | sem handler → tini é obrigatório para shutdown rápido |
| Arquivos de seed/exemplo | `*.http`, `seed*`, `fixtures/`, `popula*` | usados na validação; confira se apontam para a porta real |
| Logs | `console.log`, logger para stdout? | container deve logar em stdout/stderr |

Também verifique o histórico recente (`git log --oneline -10`): commits como "adicionando vulnerabilidades" indicam que versões antigas são intencionais — não "conserte".

## Ambiente
```bash
docker version --format '{{.Server.Version}}'
docker compose version
lsof -iTCP:<porta-app> -iTCP:<porta-banco> -sTCP:LISTEN   # vazio = livres
```
