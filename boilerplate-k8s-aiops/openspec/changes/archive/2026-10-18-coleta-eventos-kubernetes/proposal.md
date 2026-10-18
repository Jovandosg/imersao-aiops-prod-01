## Why

Hoje a descoberta de problemas no cluster é manual (`kubectl get events`, dashboards), o que leva de 30 min a 2 h para detectar um incidente. Esta change implementa o PRD 001: um coletor automático de eventos Warning que alimenta o pipeline de análise (PRD 002), reduzindo o tempo de detecção para o intervalo de coleta (3 min por padrão).

## What Changes

- Novo loop assíncrono dentro do processo FastAPI que coleta periodicamente os eventos Warning de todos os namespaces via Python SDK `kubernetes` (API `events.k8s.io/v1`).
- **Coleta imediata no startup, sem filtro temporal**: a primeira coleta roda assim que a aplicação sobe e entrega todos os Warnings ainda presentes no cluster (limitados pelo TTL de eventos do apiserver, ~1 h). Os eventos não tratados durante uma indisponibilidade continuam no cluster e são recolhidos no restart. **Difere do PRD 001**, que previa janela inicial igual ao intervalo.
- Ciclos seguintes filtram por recência a partir de uma marca d'água em memória (precedência `series.lastObservedTime` → `eventTime` → `deprecatedLastTimestamp`), com margem de sobreposição para não perder eventos que ficam visíveis na API depois da coleta. A repetição é absorvida pela deduplicação por UID do PRD 002.
- Transformação de cada evento em um dict com contrato próprio (`uid`, `type`, `reason`, `message`, `namespace`, `involved_object`, `timestamp`), desacoplado do SDK.
- Nova classe `EventHandler` com `async def handle(events: list[dict]) -> None`; implementação placeholder que imprime o batch no stdout. Despacho fire-and-forget via `asyncio.create_task`.
- Intervalo configurável por `EVENT_COLLECTION_INTERVAL_MINUTES` (padrão 3; valor inválido cai no padrão com warning).
- Tratamento de erros de conectividade e de RBAC sem interromper o loop.
- Nova dependência: `kubernetes`.

## Capabilities

### New Capabilities
- `coleta-eventos`: coleta periódica de eventos Warning do cluster, janela temporal por marca d'água, contrato de saída do evento e despacho assíncrono ao `EventHandler`.

### Modified Capabilities
<!-- Nenhuma: não há specs existentes em openspec/specs/. -->

## Impact

- **Código**: `src/my_agent_app/collector/` (loop, filtro, transformação), `src/my_agent_app/agents/` ou `collector/` (placeholder do `EventHandler`), `src/my_agent_app/main.py` (iniciar e encerrar o loop no `lifespan`).
- **Dependências**: adiciona `kubernetes` ao `pyproject.toml`.
- **Configuração**: nova env var `EVENT_COLLECTION_INTERVAL_MINUTES` (documentar em `.env.example` e `CLAUDE.md`).
- **Cluster**: exige permissão `list` em `events` (grupo `events.k8s.io`) em todos os namespaces, seja via ClusterRole (in-cluster) ou via kubeconfig local.
- **PRD 002**: no startup ele recebe um batch maior (até ~1 h de Warnings). Eventos ligados a relatórios CORRIGIDO serão reanalisados após um restart; isso fica como pendência a tratar no PRD 002.
- **Premissa**: uma única instância da aplicação por cluster. Com várias réplicas, cada uma coletaria os mesmos eventos.
