# INC-2508 — Transações aprovadas sem checagem antifraude

> Post-mortem interno. Encerrado.

**Data:** 2026-06-27
**Duração:** 3h40 (detecção só no dia seguinte)
**Severidade:** P2
**Responsável:** @carla.ops

**Resumo:** O provedor do `antifraude-gw` degradou e passou a responder acima
dos 3 segundos de timeout. Como a integração **falha aberta**, o
`pagamentos-api` aprovou 8.947 transações sem nenhuma checagem antifraude. Não
houve indisponibilidade: do ponto de vista do cliente, tudo funcionou.

**Timeline:**
- 02:10 — Latência p99 do `antifraude-gw` sobe de 340ms para mais de 3s
- 02:11 — Primeiras chamadas estouram o timeout de 3s e seguem aprovadas
- 05:50 — Latência do provedor normaliza sozinha
- (nenhum alerta disparou em nenhum momento)
- 14:20 do dia seguinte — Conciliação diária do financeiro aponta volume anômalo de aprovações sem escore de risco
- 15:05 — Plantão acionado e janela de exposição delimitada

**Causa raiz:** A falha aberta do `antifraude-gw` é decisão deliberada,
registrada na **ADR-0042**: bloquear pagamento por indisponibilidade de
antifraude custa mais receita do que o risco de fraude na janela. A decisão está
correta; o que faltava era **visibilidade** — não existe alerta para o serviço
estar operando em modo aberto, então a janela passou despercebida por 12 horas.

**Impacto:** 8.947 transações sem checagem, R$ 62.400 em chargebacks confirmados
nos 45 dias seguintes.

**Ações corretivas:**
- [x] Criar alerta de taxa de falha aberta do `antifraude-gw` acima de 1% por 5 minutos — @carla.ops — concluída em 2026-07-02
- [x] Relatório diário de transações aprovadas sem escore de risco — @ana.sre — concluída em 2026-07-09
- [ ] Reavaliar a ADR-0042 com o time de risco — @bruno.dev — **em aberto**

**Observação:** falha aberta não aparece em nenhum painel de disponibilidade. As
métricas do `pagamentos-api` ficaram verdes a noite inteira.
