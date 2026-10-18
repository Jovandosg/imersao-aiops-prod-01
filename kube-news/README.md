# Kube-News

Uma aplicação de notícias desenvolvida em NodeJS para demonstrar o uso de containers e Kubernetes.

## 📋 Sobre o Projeto

O projeto Kube-News é uma aplicação web simples desenvolvida em Node.js, projetada como exemplo para demonstrar o uso de contêineres. É um portal de notícias que permite criar, visualizar e gerenciar artigos através de uma interface web.

### 🚀 Funcionalidades Principais

- Listagem de notícias na página inicial
- Criação de novas notícias através de formulário
- Visualização detalhada de cada notícia
- API REST para inserção em massa de notícias
- Endpoints de health check para monitoramento
- Coleta de métricas para Prometheus

## 🛠️ Tecnologias Utilizadas

- **Backend**: Node.js com Express.js
- **Frontend**: EJS (Embedded JavaScript) como motor de templates
- **Banco de Dados**: PostgreSQL com Sequelize ORM
- **Monitoramento**: Prometheus (via express-prom-bundle)

## 📦 Estrutura do Projeto

```
/
├── src/                      # Código-fonte principal
│   ├── models/               # Modelos de dados
│   │   └── post.js           # Definição do modelo Post
│   ├── views/                # Templates EJS
│   │   ├── partial/          # Componentes parciais (header, footer)
│   │   ├── edit-news.ejs     # Formulário de edição
│   │   ├── index.ejs         # Página principal
│   │   └── view-news.ejs     # Visualização de notícia
│   ├── static/               # Arquivos estáticos (CSS, imagens)
│   ├── middleware.js         # Middlewares personalizados
│   ├── server.js             # Ponto de entrada da aplicação
│   ├── system-life.js        # Endpoints de health check
│   └── package.json          # Dependências
├── popula-dados.http         # Arquivo para popular o banco com dados de exemplo
└── README.md                 # Documentação
```

## 🔧 Configuração

### Pré-requisitos

- Node.js
- PostgreSQL
- Docker (opcional, para containerização)
- Kubernetes (opcional, para orquestração)

### Variáveis de Ambiente

Para configurar a aplicação, defina as seguintes variáveis de ambiente:

| Variável | Descrição | Valor Padrão |
|----------|-----------|--------------|
| DB_DATABASE | Nome do banco de dados | kubedevnews |
| DB_USERNAME | Usuário do banco de dados | kubedevnews |
| DB_PASSWORD | Senha do usuário | Pg#123 |
| DB_HOST | Endereço do banco de dados | localhost |
| DB_PORT | Porta do banco de dados | 5432 |
| DB_SSL_REQUIRE | Habilitar SSL para conexão | false |

## 🚀 Instalação e Execução

### Execução Local

1. Clone o repositório
2. Instale as dependências:
   ```bash
   cd src
   npm install
   ```
3. Configure as variáveis de ambiente necessárias
4. Inicie a aplicação:
   ```bash
   npm start
   ```
5. Acesse a aplicação em [http://localhost:8080](http://localhost:8080)

### Docker Compose (desenvolvimento)

Sobe a app (`src/Dockerfile.dev`, com hot-reload por `node --watch`) e o PostgreSQL 18, com volume nomeado:

```bash
docker compose up --build
# app em http://localhost:8080
docker compose down      # mantém os dados; use -v para apagar o volume
```

### Kubernetes local com kind

Valida a imagem de produção e o manifesto `k8s/kube-news.yaml` (ver [ADR 009](docs/adrs/009-validacao-local-kind-nodeport.md)). A app fica em http://localhost:8081 (nodePort 30080).

```bash
docker build -t fabricioveronez/kube-news-aiops:1.0.0 src/
kind create cluster --name kube-news --config k8s/kind-config.yaml
kind load docker-image fabricioveronez/kube-news-aiops:1.0.0 --name kube-news
# aplique k8s/kube-news.yaml pelo MCP Kubernetes (contexto kind-kube-news)
```

Validação: rollout 2/2; balanceamento (`curl` em loop em `/health` alterna o `machine`); `PUT /unreadyfor/60` tira um pod dos endpoints; `PUT /unhealth` reinicia o pod. O Postgres do cluster não tem volume: ao recriá-lo, faça `rollout restart` do Deployment `kube-news`.

Para remover: `kind delete cluster --name kube-news`.

### População de Dados de Exemplo

Utilize o arquivo `popula-dados.http` para inserir notícias de exemplo:

```bash
# Com uma ferramenta como o REST Client no VS Code ou curl
POST http://localhost:8080/api/post
Content-Type: application/json
# Conteúdo do arquivo popula-dados.http
```

## 📊 Monitoramento e Health Checks

A aplicação disponibiliza endpoints para monitoramento e também recursos para simular cenários de falha, muito úteis para testar a resiliência em ambientes Kubernetes:

### Endpoints de Monitoramento
- `/health` - Verifica o estado atual da aplicação (retorna status da aplicação e hostname da máquina)
- `/ready` - Verifica se a aplicação está pronta para receber tráfego
- `/metrics` - Métricas do Prometheus (geradas pelo express-prom-bundle)

### Simulação de Falhas (Chaos Engineering)
- `/unhealth` - (PUT) Altera o estado da aplicação para não saudável. Todas as requisições subsequentes receberão status code 500.
- `/unreadyfor/:seconds` - (PUT) Simula indisponibilidade temporária por um número específico de segundos. Durante este período, o endpoint `/ready` retornará status code 500.

Estes recursos de simulação de falhas são extremamente úteis para testar:
- Comportamento de probes de liveness e readiness no Kubernetes
- Políticas de retry e circuit breaker
- Mecanismos de failover
- Resiliência geral da sua infraestrutura

## 🔒 Modelo de Dados

O projeto utiliza um único modelo `Post` com os seguintes campos:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| title | String | Título da notícia (limite: 30 caracteres) |
| summary | String | Resumo da notícia (limite: 50 caracteres) |
| content | String | Conteúdo completo (limite: 2000 caracteres) |
| publishDate | Date | Data de publicação |


