# INC-2661 — Teto de conexões estourado pelo lado do faturamento-worker

> Post-mortem interno. Encerrado.

**Data:** 2026-08-11
**Duração:** 1h05
**Severidade:** P1
**Responsável:** @bruno.dev

**Resumo:** Para drenar o backlog do fechamento mensal, o pool do
`faturamento-worker` foi elevado de 15 para 25 conexões "por algumas horas". O
teto de 100 do `db-financeiro` estourou e desta vez quem caiu foi o
`pagamentos-api`. Mesmo sintoma do **INC-2417**, com os papéis invertidos.

**Timeline:**
- 22:15 — Pool do `faturamento-worker` alterado de 15 para 25 no ConfigMap, sem PR e sem revisão da Squad Cobrança
- 22:19 — `conexões ativas` do `db-financeiro` chega a 100
- 22:23 — `pagamentos-api` começa a devolver 503 intermitente em `POST /v1/cobrancas`
- 22:31 — Alerta de taxa de erro 5xx do `pagamentos-api`
- 22:38 — Plantão acionado
- 22:57 — Plantão consulta o documento de projeto e encontra a conta de conexões
- 23:08 — Pool do `faturamento-worker` revertido para 15
- 23:20 — Conexões caem para 78 e os dois serviços normalizam

**Causa raiz:** A conta do `db-financeiro` fecha **exatamente** em 100, sem
folga. Aumentar o pool de qualquer um dos dois lados estoura o teto — a única
diferença é quem cai primeiro. Não houve nenhum aviso antes do erro de cliente
porque **o alarme de `conexões ativas > 85`, registrado como ação de prevenção
no INC-2417, nunca foi implementado**.

**Ações corretivas:**
- [ ] Implementar o alarme de `conexões ativas > 85` — @ana.sre — **reaberta do INC-2417, agora com prazo: até 2026-08-22**
- [x] Pool do `faturamento-worker` fixado em 15 no overlay de produção, alterável só por PR — @bruno.dev — concluída em 2026-08-13
- [ ] Incluir a conta de conexões no checklist de revisão de ConfigMap — @carla.ops — **em aberto**

**Observação:** o documento de projeto trata o `db-financeiro` compartilhado
como dívida de roadmap, sem data. Estes dois incidentes são o custo já pago por
essa dívida — dois P1 em três meses —, e a ação de prevenção do INC-2417 segue
aberta desde 2026-05-19.
