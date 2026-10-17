# Projeto — pagamentos-api

> Documento interno da Squad Cobrança. Última revisão: 2026-08-04.

## Identificação

| | |
|---|---|
| Serviço | `pagamentos-api` |
| Time responsável | Squad Cobrança |
| On-call | rodízio semanal da squad, escalonamento em 15 min |
| Criticidade | tier 1 — indisponibilidade bloqueia receita |
| Repositório | `interno/pagamentos-api` |

## O que a aplicação faz

Recebe e processa cobranças (`POST /v1/cobrancas`), consulta risco no
`antifraude-gw` e grava no `db-financeiro`. A **conciliação de cobranças** roda
dentro do mesmo processo, em workers paralelos, e drena a fila noturna.

Isso importa mais do que parece: a conciliação **consome do mesmo pool de
conexões** que atende as requisições HTTP. Subir o paralelismo da conciliação
consome banco exatamente como subir réplica.

## Stack

| | |
|---|---|
| Linguagem | Go 1.23 |
| Banco | PostgreSQL 16 (`db-financeiro`) |
| Mensageria | RabbitMQ (`fila-cobrancas`) |
| Runtime | Kubernetes, 4 réplicas em produção |
| Observabilidade | métricas Prometheus em `/metrics`, logs em JSON |

## Como executar localmente

```bash
git clone git@interno:pagamentos-api.git
cd pagamentos-api

make deps          # sobe postgres e rabbitmq via docker compose
make migrate       # aplica as migrações em migrations/
make dev           # sobe a api em http://localhost:8080

make test          # testes unitários
make test-integracao   # exige o `make deps` de pé
```

O `make dev` **não** sobe o `antifraude-gw`: em ambiente local a integração cai
no stub, que aprova tudo. Para testar recusa, use `ANTIFRAUDE_MODO=stub-recusa`.

## Variáveis de ambiente

| Variável | Padrão | Observação |
|---|---|---|
| `PORT` | `8080` | |
| `DB_DSN` | — | obrigatória |
| `DB_MAX_OPEN_CONNS` | `20` | **pool por réplica — ver a seção do banco** |
| `DB_MAX_IDLE_CONNS` | `5` | |
| `RABBIT_URL` | — | obrigatória |
| `ANTIFRAUDE_URL` | — | vazia em local, cai no stub |
| `ANTIFRAUDE_TIMEOUT` | `3s` | falha **aberta** ao estourar — ver ADR-0042 |
| `CONCILIACAO_WORKERS` | `4` | paralelismo da conciliação noturna |
| `LOG_LEVEL` | `info` | `debug` em produção enche o disco do nó |

## Dependências

| Dependência | Tipo | Observação |
|---|---|---|
| `db-financeiro` | PostgreSQL 16 | **compartilhado com `faturamento-worker`** |
| `fila-cobrancas` | RabbitMQ | consumo assíncrono, não bloqueia o request |
| `antifraude-gw` | HTTP externo | timeout de 3s, falha aberta |

## Banco de dados — os números que importam

O `db-financeiro` é **compartilhado**. Isso é dívida conhecida, registrada em
ADR-0031, e a separação está no roadmap sem data.

| | |
|---|---|
| `max_connections` do cluster | **100** |
| Pool do `pagamentos-api` (`DB_MAX_OPEN_CONNS`) | **20 conexões por réplica** |
| Réplicas do `pagamentos-api` em produção | **4** (portanto até 80 conexões) |
| Reserva do `faturamento-worker` | **15 conexões** |
| Reserva para manutenção e superusuário | **5** |

**A soma fecha exatamente em 100.** Não há folga. Qualquer aumento de réplica,
de `CONCILIACAO_WORKERS` ou de `DB_MAX_OPEN_CONNS` — em qualquer um dos dois
serviços — estoura o teto e derruba os dois, o outro primeiro, porque a reserva
dele é menor.

O sintoma dessa exaustão é sempre o mesmo: `timeout acquiring connection from
pool` no log da aplicação e `conexões ativas` cravado em 100 no banco, com CPU
e memória do container normais.

## Deploy e rollback

O `pagamentos-api` faz rollback por tag de imagem, nunca por `git revert`:

1. Identificar a tag anterior estável em `interno/pagamentos-api/releases`
2. Aplicar a tag anterior no deployment
3. Aguardar as 4 réplicas subirem antes de declarar resolvido
4. Migração de banco **não** é revertida automaticamente — conferir em
   `migrations/` se a versão que sai criou schema

**Rollback é decisão do on-call e dispensa aprovação** fora do horário
comercial.

## Janela de manutenção

Terças, 02:00–04:00 (BRT). Fora dela, qualquer mudança em produção exige
aprovação do tech lead da squad — exceto rollback.

## Decisões registradas

| ADR | Assunto |
|---|---|
| ADR-0031 | manter o `db-financeiro` compartilhado até a separação entrar no roadmap |
| ADR-0042 | `antifraude-gw` falha **aberta**: indisponibilidade de antifraude não bloqueia pagamento |

## O que este documento não cobre

- Ajuste de `max_connections`, que é do time de Plataforma e passa por chamado.
- Histórico de incidentes — os post-mortems ficam em documentos próprios.
