# INC-2417 — Esgotamento de conexões do db-financeiro

> Post-mortem interno. Encerrado.

**Data:** 2026-05-19
**Duração:** 52 minutos
**Severidade:** P1
**Responsável:** @ana.sre

**Resumo:** Uma subida de 3 para 5 réplicas do `pagamentos-api`, em horário de
pico, esgotou o `max_connections` do `db-financeiro`. O `faturamento-worker`
parou primeiro, por ter a reserva menor. Resolvido com rollback do número de
réplicas.

**Timeline:**
- 18:40 — Deploy de escala do `pagamentos-api`: 3 réplicas para 5, para absorver o pico da campanha de meio de mês
- 18:44 — `conexões ativas` do `db-financeiro` sobe de 71 para 100 e trava
- 18:47 — `faturamento-worker` começa a registrar `timeout acquiring connection from pool`
- 18:51 — Fila de cobranças do `faturamento-worker` passa de 6 mil mensagens
- 18:58 — Alerta de taxa de erro do `pagamentos-api` acima de 5%
- 19:03 — Plantão acionado
- 19:19 — Identificada a relação entre o deploy de escala e o teto de conexões
- 19:26 — Rollback para 3 réplicas
- 19:32 — Conexões caem para 74 e os dois serviços normalizam

**Causa raiz:** O `db-financeiro` tem `max_connections = 100` e é compartilhado.
Com pool de 20 conexões por réplica, 5 réplicas do `pagamentos-api` consomem as
100 sozinhas — não sobra nada para as 15 do `faturamento-worker` nem para as 5
de manutenção. A conta não foi verificada antes do deploy de escala porque ela
não estava escrita em lugar nenhum.

**Ações corretivas:**
- [x] Registrar a conta de conexões no documento de projeto do `pagamentos-api` — @ana.sre — concluída em 2026-05-22
- [ ] Criar alarme sobre `conexões ativas > 85` no `db-financeiro` — @ana.sre — **não implementada**
- [x] Exigir revisão da Squad Cobrança em qualquer mudança de contagem de réplicas — @carla.ops — concluída em 2026-05-26

**Observação do plantão:** o sintoma no log do `pagamentos-api` é idêntico ao de
uma indisponibilidade do banco — `timeout acquiring connection from pool` — mas
CPU e memória do container ficam normais o tempo todo. É o que distingue os dois
casos.
