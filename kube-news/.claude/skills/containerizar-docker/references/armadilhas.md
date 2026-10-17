# Armadilhas de container (aprendidas na prática)

| Sintoma | Causa | Tratamento |
|---|---|---|
| CSS/imagens 404 ou "Failed to lookup view" | paths relativos ao cwd (`express.static('static')`, `views/`) e `WORKDIR` apontando para o lugar errado | Dockerfile no diretório da app, `WORKDIR /app`, `COPY . .` desse diretório |
| App sai logo após subir com erro de conexão / unhandled rejection | init depende do banco (ex.: `sequelize.sync()` sem await) e o banco ainda não aceita conexões | `healthcheck` no banco + `depends_on: condition: service_healthy` (no K8s: initContainer) |
| `docker compose stop` leva ~10s; restart no K8s leva +30s | processo da app é PID 1 e ignora SIGTERM | `tini` como ENTRYPOINT (ou `init: true` no compose quando não der para instalar) |
| Seed falha com connection refused | arquivo de exemplo (`*.http`) aponta para outra porta (ex.: 4503 vs 8080 real) | usar a porta real; reportar a divergência |
| Senha do banco no compose/código | defaults fixos no código | aceitável em laboratório; reportar e sugerir `.env`/secrets |
| Dependências antigas/vulneráveis | pode ser proposital (demo de scanning) | não atualizar sem pedir; reportar |
| `npm start` não encerra limpo | npm não repassa sinais | `CMD ["node", "<entry>.js"]` |
| App inacessível de fora do container | bind em `127.0.0.1` | bind em `0.0.0.0` (via env/flag, sem mudar código se possível) |
| Porta já em uso no host | outro serviço/compose antigo | `lsof -iTCP:<porta> -sTCP:LISTEN`; trocar só o lado host do mapeamento |
