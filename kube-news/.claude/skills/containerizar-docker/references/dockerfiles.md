# Templates de Dockerfile por stack

Todos seguem o mesmo esqueleto: base slim/alpine LTS → deps antes do código → só produção → tini → non-root → porta real. O contexto de build é o **diretório da app** (onde o Dockerfile fica).

Antes de fixar a versão da base, confira o ciclo de vida da linguagem contra a data de hoje — prefira a LTS ativa (não a que já está em manutenção/EOL).

## Node.js (referência — validado no kube-news)
```dockerfile
FROM node:22-alpine

RUN apk add --no-cache tini

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

USER node

EXPOSE 8080

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "server.js"]
```
- `WORKDIR /app` + `COPY . .` do diretório da app → `static/` e `views/` ficam no cwd (paths relativos funcionam).
- Sem `package-lock.json`, use `npm install --omit=dev` e aponte no relatório.
- `CMD` chama `node` direto, não `npm start` (npm não repassa sinais bem).
- Usuário `node` (uid 1000) já existe na imagem oficial.

`.dockerignore`:
```
node_modules
npm-debug.log
Dockerfile
.dockerignore
```

## Python (Flask/FastAPI/Django)
```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --uid 1000 --create-home app
USER app

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
```
- FastAPI: `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`. Django: `gunicorn projeto.wsgi`.
- Bind em `0.0.0.0` — `127.0.0.1` dentro do container é inacessível de fora.
- Poetry/uv: exporte para requirements ou instale a ferramenta numa etapa de build.

`.dockerignore`: `__pycache__`, `*.pyc`, `.venv`, `venv`, `.pytest_cache`, `Dockerfile`, `.dockerignore`

## Go
```dockerfile
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app

FROM alpine:3.20
RUN apk add --no-cache tini ca-certificates
WORKDIR /app
COPY --from=build /out/app ./app
# copie aqui pastas lidas em runtime (templates/, static/)
USER 1000
EXPOSE 8080
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["./app"]
```
- Multi-stage: o binário estático vai para uma imagem mínima.
- Ajuste `./cmd/app` para o pacote main real.

## Java (Spring Boot, Maven)
```dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q package -DskipTests

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache tini
WORKDIR /app
COPY --from=build /src/target/*.jar app.jar
USER 1000
EXPOSE 8080
ENTRYPOINT ["/sbin/tini", "--", "java", "-jar", "app.jar"]
```
- Health no Spring: `/actuator/health` (liveness/readiness em `/actuator/health/liveness|readiness` se habilitado).
- Gradle: troque a etapa de build por `gradle bootJar`.

## Outras stacks
Aplique o mesmo esqueleto e explique no relatório qualquer desvio (ex.: imagem distroless sem shell → tini não disponível; use `docker run --init` / `init: true` no compose e, no K8s, garanta que a app trata SIGTERM).
