## Context

O boilerplate tem FastAPI com `lifespan` em `src/my_agent_app/main.py`, e o módulo `collector/` existe mas está vazio. O PRD 001 define a coleta, e o PRD 002 consome os eventos via `EventHandler` e faz a deduplicação por `metadata.uid`, ignorando UIDs ligados a relatórios ativos. A coleta usa o SDK `kubernetes`; o MCP fica reservado aos agentes.

## Goals / Non-Goals

**Goals:**
- Loop de coleta não bloqueante, iniciado e encerrado pelo `lifespan`.
- Não perder eventos Warning por causa do restart nem da corrida entre a escrita na API e a coleta. Aceitamos entrega repetida, que a deduplicação do 002 absorve.
- Contrato de saída estável e testável, desacoplado do SDK.

**Non-Goals:**
- Persistir eventos brutos, deduplicar, coletar eventos Normal, multi-cluster, múltiplas réplicas, paginação e watch.

## Decisions

### D1. Estrutura de módulos
```
collector/
├── config.py      # leitura de EVENT_COLLECTION_INTERVAL_MINUTES
├── k8s.py         # load_incluster_config → load_kube_config; list de eventos
├── transform.py   # recência (precedência) + evento SDK → dict do contrato
├── handler.py     # EventHandler (placeholder: print)
└── loop.py        # EventCollector: ciclo, marca d'água, despacho
```
`transform.py` contém funções puras, o que concentra os testes de precedência e de contrato sem precisar de cluster. O `EventHandler` fica em `collector/handler.py` por enquanto; o PRD 002 pode substituí-lo injetando outra implementação no `EventCollector`.

### D2. Coleta imediata, sem filtro no startup
Ordem do ciclo: **coletar → despachar → dormir**. Na primeira execução a marca d'água é `None`, e então nenhum filtro de recência é aplicado. Os eventos que surgiram enquanto a app estava fora do ar continuam no cluster até o TTL do apiserver (~1 h) e são recolhidos no start. O custo é só um atraso maior para eles.
*Alternativa descartada:* janela inicial igual ao intervalo (texto original do PRD 001), que perde os eventos do período de indisponibilidade.

### D3. Marca d'água com sobreposição
- `inicio = now(UTC)` capturado **antes** do `list()`.
- Filtro: `recencia >= marca - intervalo` (comparação inclusiva, porque `deprecatedLastTimestamp` tem resolução de segundos).
- Depois de um `list()` bem-sucedido: `marca = inicio`.

A sobreposição de um intervalo cobre o atraso entre a ocorrência e a visibilidade na API, além de diferenças de relógio entre nós e a aplicação. Cada evento pode ser entregue até duas vezes, e a deduplicação por UID do 002 descarta a repetição.
*Alternativas:* (a) sem sobreposição, que perde one-shots silenciosamente; (b) watch com `resourceVersion`, que é exato mas exige tratar 410 Gone e reconexão, complexidade injustificada para a v1.

### D4. Filtro de tipo no servidor
`list_event_for_all_namespaces(field_selector="type=Warning")` reduz o volume trafegado. O filtro de recência é feito no cliente, porque field selectors não comparam datas. Se o selector for rejeitado pelo apiserver, o filtro de tipo passa para o cliente (ver Open Questions).

### D5. Chamada não bloqueante ao SDK
Padrão: `kubernetes` síncrono executado via `asyncio.to_thread`. A documentação atual do client lista um módulo `kubernetes.aio`; se ele estiver disponível e estável na versão instalada, pode substituir o `to_thread`. A escolha fica isolada em `k8s.py`.

### D6. Fire-and-forget seguro
- As tasks do handler ficam num `set` com referência forte e são removidas via `add_done_callback`, evitando que o GC as colete no meio da execução.
- Um wrapper captura e loga qualquer exceção de `handle()`.
- No shutdown (`lifespan` após o `yield`), o loop é cancelado e as tasks pendentes são canceladas. O PRD 002 recupera relatórios EM_ANALISE órfãos no startup.

### D7. Intervalo
`float(env)`; se der erro ou o valor for `<= 0`, usa 3 com warning. Aceitar frações permite testes rápidos.

### D8. Estratégia de testes e validação
Três camadas:

```
┌─────────────────────┬──────────────────────────────┬─────────────────────────┐
│ Camada              │ O que cobre                  │ Como                    │
├─────────────────────┼──────────────────────────────┼─────────────────────────┤
│ Unitário (pytest)   │ precedência, contrato,       │ funções puras + fake de │
│                     │ janela/sobreposição, config, │ listagem e handler      │
│                     │ loop (não bloqueia, erros)   │ (sem cluster)           │
├─────────────────────┼──────────────────────────────┼─────────────────────────┤
│ Integração (kind)   │ listagem real, field         │ pytest marker `kind`,   │
│                     │ selector, só Warning, todos  │ aplica manifestos de    │
│                     │ os namespaces, contrato real │ manifestos-k8s/         │
├─────────────────────┼──────────────────────────────┼─────────────────────────┤
│ Validação E2E       │ app rodando via uvicorn,     │ roteiro manual com kind │
│ (manual)            │ startup, ciclos, stdout,     │ + checklist de          │
│                     │ RBAC, cluster fora do ar     │ resultados esperados    │
└─────────────────────┴──────────────────────────────┴─────────────────────────┘
```

**Cluster de teste:** kind local (`kind create cluster --name aiops`). A app roda fora do cluster e autentica pelo kubeconfig do contexto `kind-aiops`.

**Manifestos de teste** (existentes em `manifestos-k8s/`):

| Manifesto | Defeito intencional | Warning esperado |
|---|---|---|
| `nginx.yaml` | imagem `ngin:latest` inexistente | `Failed` / `BackOff` (pull de imagem) no pod `nginx-*` |
| `kube-news.yaml` | `DB_PASSWORD` (`pg123`) diferente da senha do postgres (`pg1234`); 10 réplicas | `BackOff` (reinício de container) nos pods `kubenews-*`, gerando volume e eventos recorrentes com `series` |

Os manifestos são aplicados num namespace dedicado e num segundo namespace (por exemplo, `teste-a` e `teste-b`) para exercitar a cobertura de todos os namespaces. O Service `LoadBalancer` do kube-news fica em `<pending>` no kind; isso é esperado e não faz parte da validação.

**RBAC:** validado com um ServiceAccount sem permissões e um kubeconfig gerado via `kubectl create token`, apontado por `KUBECONFIG`.

**Cluster inacessível:** validado parando o container do control plane (`docker stop aiops-control-plane`) e religando em seguida.

## Risks / Trade-offs

- [Restart reentrega até ~1 h de Warnings ao 002, e eventos ligados a relatórios CORRIGIDO serão reanalisados] → Pendência registrada para o PRD 002 (por exemplo, reanalisar CORRIGIDO só quando a recência for posterior à correção).
- [App fora do ar por mais tempo que o TTL de eventos] → Eventos expirados se perdem. Risco aceito.
- [Sobreposição duplica a entrega] → Absorvida pela deduplicação do 002. Custo: uma consulta extra ao banco por ciclo.
- [Várias réplicas coletam em duplicidade, e o 002 não tem trava atômica] → Premissa de instância única, documentada.
- [Volume alto sem paginação] → O filtro `type=Warning` no servidor reduz o volume. Monitorar.
- [Concorrência ilimitada de tasks do handler durante um incidente longo] → Fora do escopo do 001; avaliar um teto no 002.
- [O kube-news pode não entrar em CrashLoop se a aplicação tolerar a falha de conexão com o banco] → O nginx garante Warnings determinísticos; o kube-news é usado como fonte de volume e de eventos recorrentes, e o resultado real é registrado na validação.

## Open Questions

- ~~O apiserver aceita `field_selector="type=Warning"` no grupo `events.k8s.io/v1`?~~ **Sim** (kind, Kubernetes do `kind create cluster` em 2026-10-18): a listagem retornou apenas eventos Warning. O filtro de tipo fica no servidor, com uma checagem defensiva no cliente.
- ~~`kubernetes.aio` está disponível na versão que o `uv add kubernetes` resolver?~~ **Sim** na 37.0.1, mas mantivemos `to_thread` (ver D9).
- Sincronizar o PRD 001 (Registro de Decisões) com D2, D3 e D7.

## Decisões tomadas na implementação

### D9. Listagem crua em vez dos models do SDK
O `kubernetes` 37.0.1 gera models pydantic, e `EventsV1Event.event_time` é obrigatório. Eventos legados (kubelet, scheduler), que são a maioria, chegam com `eventTime: null`, e por isso `list_event_for_all_namespaces()` levanta `ValidationError` em qualquer cluster real. `k8s.py` chama a API com `_preload_content=False` e devolve os dicts crus da API (camelCase). `transform.py` opera sobre esses dicts. O contrato de saída não muda e o acoplamento com o SDK diminui. Pelo mesmo motivo, o `kubernetes.aio` (mesmos models) não foi adotado: o cliente síncrono continua em `asyncio.to_thread`.

### D10. Recorrência real vem sem `series`
No kind, os eventos recorrentes do kubelet (BackOff do kube-news, Failed do nginx) chegam como eventos legados: `series` vazio e recorrência em `deprecatedCount` / `deprecatedLastTimestamp`, que é atualizado a cada repetição. A precedência continua correta (cai em `deprecatedLastTimestamp`). O teste 7.5 cria um evento `events.k8s.io/v1` sintético com `series` no apiserver real, e um teste extra cobre o BackOff recorrente via `deprecatedLastTimestamp`.

### D11. Log de falha de conectividade
Erros `urllib3.HTTPError`/`OSError` geram uma linha de log, sem traceback, porque com o cluster fora do ar o traceback se repetiria a cada ciclo. Exceções inesperadas continuam com `logger.exception`.

### D12. `sqlalchemy[asyncio]`
Correção fora do escopo, mas necessária para o shutdown limpo (8.8): no Apple Silicon (`arm64`) o marker do SQLAlchemy não instala `greenlet`, e o `engine.dispose()` do `lifespan` falhava em todo shutdown. A dependência passou a ser `sqlalchemy[asyncio]`.

## Resultado da validação (2026-10-18, kind `aiops`)

Reasons observadas em 6.4: `teste-a` → `Failed` (ErrImagePull de `ngin:latest`) e `BackOff`; `teste-b` → `BackOff` (CrashLoop do kube-news); também `FailedScheduling` enquanto o nó subia e `Unhealthy` no CoreDNS.

| Passo | Resultado |
|---|---|
| Unitários (`uv run pytest`) | 33 passed |
| Integração (`uv run pytest -m kind`) | 5 passed; pulam se o contexto ativo não for `kind-aiops` |
| 8.1 Startup | OK: primeira coleta no startup, 30 Warnings, incluindo os 25 de `teste-a`/`teste-b` criados antes do start |
| 8.2 Ciclos | OK: batches a cada 30 s só com `BackOff`/`Failed` recorrentes e 0 eventos Normal |
| 8.3 Evento novo | OK: scale para 2 réplicas às 18:18:00; os Warnings do pod `nginx-86857974b8-bghkd` saíram no ciclo das 18:18:24 |
| 8.4 Sem eventos | OK: depois do `kubectl delete ns teste-a teste-b`, nenhum batch em 4 ciclos; os 8 Warnings antigos de `kube-system` foram descartados pela janela |
| 8.5 Cluster inacessível | OK: com `docker stop` foi registrada uma linha de erro por ciclo e o loop seguiu vivo; depois do `docker start`, a coleta voltou com um batch maior, porque a marca d'água ficou parada |
| 8.6 RBAC | OK: SA sem permissão gerou `Coleta de eventos negada (HTTP 403): permissao necessaria: verbo 'list' no recurso 'events' do grupo 'events.k8s.io' (events.events.k8s.io) em todos os namespaces` a cada ciclo, com o loop vivo |
| 8.7 Intervalo inválido | OK: `EVENT_COLLECTION_INTERVAL_MINUTES invalido ('abc'); usando o padrao de 3.0 minutos` → `intervalo de 0:03:00` |
| 8.8 Shutdown | OK depois do D12: `Coletor de eventos encerrado` → `Application shutdown complete`, 0 tracebacks |

Trecho do stdout (batch real, 8.3):

```
=== 16 evento(s) Warning coletado(s) em 2026-10-18T18:18:24.982184+00:00 ===
uid=6cf723c4-61b7-468a-9b05-d5f48207811f type=Warning reason=Failed namespace=teste-a involved_object.kind=Pod involved_object.name=nginx-86857974b8-bghkd involved_object.namespace=teste-a timestamp=2026-10-18T18:18:19+00:00 message='Failed to pull image "ngin:latest": failed to pull and unpack image ...'
uid=9849f652-1818-47c3-bbb5-88b1a38f33ec type=Warning reason=Failed namespace=teste-a involved_object.kind=Pod involved_object.name=nginx-86857974b8-bghkd involved_object.namespace=teste-a timestamp=2026-10-18T18:18:19+00:00 message='Error: ErrImagePull'
```
