"""Os exemplos de post-mortem, e o incidente a documentar.

Ficam separados do `app.py` pelo mesmo motivo do `02`: e um bloco longo, e com
ele la as poucas linhas que interessam na aula estariam soterradas.

O desenho daqui e o conteudo do exemplo. Quatro decisoes sustentam a licao:

1. SAO DOIS EXEMPLOS. Um so ja e one-shot; dois e o minimo que caracteriza
   few-shot. E post-mortem e saida longa — um terceiro exemplo incha o prompt
   sem ensinar nada novo, e o custo aparece no readout.
2. AS CAUSAS SAO DIFERENTES. Certificado no primeiro, disco no segundo,
   configuracao-como-codigo no alvo. Tres exemplos da mesma causa ensinariam o
   assunto em vez do formato.
3. O MAIS COMPLETO VAI POR ULTIMO. O modelo da mais peso ao exemplo mais
   recente, entao o exemplo 2 e o que tem timeline longa, tres acoes corretivas
   e mais de um servico envolvido.
4. O ALVO NAO ESTA NO FORMATO. `INCIDENTE` sao anotacoes cruas de plantao, fora
   de ordem e sem secao nenhuma. Se ele ja viesse estruturado, os dois paineis
   sairiam parecidos e a comparacao morreria.

Os exemplos NAO podem virar o alvo. Exemplo que e o gabarito nao mede
generalizacao, mede memoria.
"""

# O formato do time inteiro mora aqui — e so aqui. O `SYSTEM_PROMPT` do
# `app.py` nao descreve secao nenhuma, de proposito: e este texto que ensina o
# formato, e e a ausencia dele que o painel da esquerda sofre.
EXEMPLOS = """
Siga o padrão dos dois post-mortems abaixo.

### Incidente: Falha na entrega de webhooks para o parceiro de cobrança
**Data:** 2026-06-03
**Duração:** 25 minutos
**Severidade:** P2
**Responsável:** @ana.sre

**Resumo:** O `notificacoes-api` parou de entregar webhooks ao parceiro de
cobrança por 25 minutos, após a expiração do certificado TLS do endpoint do
parceiro. As mensagens ficaram retidas na fila e foram reentregues depois da
correção — nenhuma foi perdida.

**Timeline:**
- 09:12 — Primeiras falhas de handshake TLS nas chamadas ao parceiro
- 09:15 — Alerta de taxa de erro do `notificacoes-api` acima de 5%
- 09:21 — Plantão acionado
- 09:26 — Identificado certificado do parceiro expirado às 00:00 UTC
- 09:31 — Parceiro contatado, novo certificado publicado
- 09:37 — Entregas normalizadas e fila drenada

**Causa raiz:** O certificado TLS do endpoint do parceiro expirou. A renovação
automática do lado dele falhava havia 3 dias, e não existe do nosso lado nenhum
alerta de validade de certificado de terceiro.

**Ações corretivas:**
- [ ] Criar alerta de certificado de parceiro com validade menor que 14 dias — @ana.sre — até 2026-06-10
- [ ] Registrar o contato de plantão do parceiro no runbook — @bruno.dev — até 2026-06-08

---

### Incidente: Interrupção do faturamento-worker por disco cheio no nó
**Data:** 2026-07-14
**Duração:** 1h10
**Severidade:** P1
**Responsável:** @bruno.dev

**Resumo:** O `faturamento-worker` ficou 1h10 sem processar. O deploy v3.2.0
subiu com `LOG_LEVEL=debug` em produção, o volume de log encheu o disco do nó
`node-ops-02` e o kubelet passou a evictar os pods por disk pressure. A
`fila-cobrancas` acumulou 41 mil mensagens, todas processadas depois da
normalização.

**Timeline:**
- 21:40 — Deploy do `faturamento-worker` v3.2.0
- 22:05 — Uso de disco do `node-ops-02` sobe de 70% para 92%
- 22:18 — Kubelet reporta DiskPressure e começa a evictar pods
- 22:26 — Alerta de profundidade da `fila-cobrancas` acima do limite
- 22:31 — Plantão acionado
- 22:52 — Identificado `LOG_LEVEL=debug` no ConfigMap promovido junto com o deploy
- 23:05 — Rollback para v3.1.4 e limpeza de `/var/log` no nó
- 23:36 — Fila drenada e processamento normalizado

**Causa raiz:** O `LOG_LEVEL=debug` usado em homologação foi promovido junto com
o manifesto para produção. Em debug o `faturamento-worker` gera cerca de 40x
mais log, e a rotação configurada no nó não absorve esse volume.

**Ações corretivas:**
- [ ] Fixar `LOG_LEVEL=info` no overlay de produção — @bruno.dev — até 2026-07-16
- [ ] Criar alerta de disco do nó acima de 80% — @ana.sre — até 2026-07-18
- [ ] Comparar ConfigMap de homologação e produção no pipeline — @carla.ops — até 2026-07-24
"""

# Anotacoes cruas, na ordem em que a pessoa lembrou. Nenhuma secao, nenhum
# rotulo, nenhuma data no formato do time — o painel da esquerda vai ter que
# inventar tudo isso, e vai inventar diferente.
INCIDENTE = """
Anotações do plantão — Squad Cobrança, 2026-08-19

- Por volta de 01:50 a fila-cobrancas começou a reentregar mensagem que já
  tinha sido processada. Cliente abriu chamado reclamando de cobrança
  duplicada.
- A mudança que entrou foi no Terraform da fila, aplicada 01:38: mexeram na
  policy de retry e o ack timeout caiu de 5 min para 30s, enquanto ajustavam
  outra coisa no mesmo módulo.
- Cada lote de cobrança leva uns 90s para processar. Com timeout de 30s, todo
  lote estourava e voltava para a fila. Reentrega em loop por quase 2h.
- Só descobrimos 03:20, olhando o diff do terraform plan da madrugada.
  Revertido 03:35. Fila normalizou 03:47.
- 1.284 cobranças duplicadas geradas. O time financeiro estornou tudo à mão no
  dia seguinte.
- Plantão: @carla.ops.
- Ninguém percebeu antes porque não existe alerta de taxa de reentrega.
"""
