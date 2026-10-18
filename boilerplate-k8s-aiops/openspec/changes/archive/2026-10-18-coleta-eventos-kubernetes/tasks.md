## 1. Setup

- [x] 1.1 Adicionar a dependência `kubernetes` (`uv add kubernetes`) e verificar se `kubernetes.aio` está disponível na versão resolvida (D5)
- [x] 1.2 Adicionar `pytest` e `pytest-asyncio` como dependências de desenvolvimento e criar `tests/`
- [x] 1.3 Criar a estrutura `collector/` com `config.py`, `k8s.py`, `transform.py`, `handler.py` e `loop.py` (D1)

## 2. Configuração e acesso ao cluster

- [x] 2.1 Implementar a leitura de `EVENT_COLLECTION_INTERVAL_MINUTES` (float, padrão 3, warning para inválido, zero ou negativo) com testes
- [x] 2.2 Implementar a autenticação `load_incluster_config()` → `load_kube_config()` em `k8s.py`
- [x] 2.3 Implementar a listagem não bloqueante via `EventsV1Api.list_event_for_all_namespaces(field_selector="type=Warning")` (`to_thread` ou `aio`)
- [x] 2.4 Validar em cluster de teste se o field selector `type=Warning` é aceito; se não for, mover o filtro de tipo para o cliente (Open Question)

## 3. Transformação e filtro

- [x] 3.1 Implementar a função de recência com precedência `series.lastObservedTime` → `eventTime` → `deprecatedLastTimestamp`, retornando `None` quando nenhum existir
- [x] 3.2 Implementar o mapeamento do evento SDK para o dict do contrato (`note` → `message`, `regarding` → `involved_object`, namespace vazio para cluster-scoped, `timestamp` em ISO 8601)
- [x] 3.3 Implementar o filtro de janela: sem filtro quando a marca d'água é `None`; caso contrário, `recencia >= marca - intervalo`; descartar sem timestamp com warning no log
- [x] 3.4 Testes unitários de precedência (series com eventTime antigo, sem series, legado sem eventTime, sem nenhum), de contrato e de janela (incluindo a sobreposição e o caso de startup)

## 4. Handler e loop

- [x] 4.1 Criar `EventHandler` com `async def handle(events: list[dict]) -> None` que imprime no stdout um cabeçalho (quantidade e instante da coleta) e uma linha por evento com todos os campos do contrato; teste com `capsys`
- [x] 4.2 Implementar `EventCollector`: ciclo coletar → despachar → dormir, primeira coleta imediata, `inicio` capturado antes do `list()`, marca d'água avançando só após `list()` bem-sucedido
- [x] 4.3 Implementar o despacho fire-and-forget: `asyncio.create_task` com wrapper que loga exceções, `set` de referências fortes com `add_done_callback`, sem invocar o handler em batch vazio
- [x] 4.4 Tratar erros de conectividade e `ApiException` 401/403 (mensagem com a permissão `list` em `events.events.k8s.io`), mantendo o loop vivo e a marca d'água inalterada
- [x] 4.5 Testes do loop com fake de listagem e handler lento ou com erro: não bloqueia, erro isolado, marca d'água não avança em falha, primeira coleta imediata

## 5. Integração com a aplicação

- [x] 5.1 Iniciar o `EventCollector` no `lifespan` de `main.py` e, no shutdown, cancelar o loop e as tasks pendentes do handler
- [x] 5.2 Documentar `EVENT_COLLECTION_INTERVAL_MINUTES` em `.env.example` e na tabela de variáveis do `CLAUDE.md`
- [x] 5.3 Documentar a ClusterRole mínima (`list` em `events.events.k8s.io`) em `manifestos-k8s/` ou no README, e a premissa de instância única

## 6. Ambiente de teste com kind

- [x] 6.1 Criar o cluster local `kind create cluster --name aiops` e confirmar o contexto `kind-aiops` (`kubectl cluster-info --context kind-aiops`)
- [x] 6.2 Criar os namespaces `teste-a` e `teste-b`
- [x] 6.3 Aplicar `manifestos-k8s/nginx.yaml` em `teste-a` e `manifestos-k8s/kube-news.yaml` em `teste-b`
- [x] 6.4 Confirmar com `kubectl get events -A --field-selector type=Warning` que os Warnings esperados existem (pull de imagem do nginx; BackOff do kube-news), registrando quais reasons apareceram de fato
- [x] 6.5 Documentar o roteiro de setup e teardown do kind (`kind delete cluster --name aiops`) no README

## 7. Testes de integração com kind

- [x] 7.1 Configurar o marker pytest `kind` e excluí-lo da execução padrão (rodar com `uv run pytest -m kind`)
- [x] 7.2 Teste: a listagem real com `field_selector="type=Warning"` é aceita pelo apiserver e retorna só eventos Warning (fecha a Open Question de D4)
- [x] 7.3 Teste: a coleta retorna eventos dos namespaces `teste-a` e `teste-b`
- [x] 7.4 Teste: cada evento coletado do nginx valida contra o contrato de saída (chaves, tipos, `involved_object.kind == "Pod"`, `timestamp` em ISO 8601)
- [x] 7.5 Teste: um evento com `series` usa `series.lastObservedTime` como `timestamp` (evento v1 sintético; o kubelet não preenche `series`, ver D10) e o BackOff recorrente do kube-news usa `deprecatedLastTimestamp`
- [x] 7.6 Rodar a suíte completa (`uv run pytest` e `uv run pytest -m kind`) e garantir que tudo está verde

## 8. Validação end-to-end (app rodando, saída no stdout)

- [x] 8.1 Startup: com os manifestos já aplicados, subir a app com `EVENT_COLLECTION_INTERVAL_MINUTES=0.5` e confirmar no stdout que a primeira coleta é imediata e contém os Warnings criados antes do start
- [x] 8.2 Ciclos: aguardar pelo menos 2 ciclos e confirmar no stdout novos batches com os eventos recorrentes (BackOff) e nenhum evento Normal
- [x] 8.3 Evento novo durante a execução: escalar o nginx (`kubectl scale deploy/nginx -n teste-a --replicas=2`) e confirmar que os Warnings do novo pod aparecem no stdout no ciclo seguinte
- [x] 8.4 Sem eventos: corrigir os manifestos (ou apagar os namespaces), aguardar a janela passar e confirmar que nenhum batch é impresso
- [x] 8.5 Cluster inacessível: `docker stop aiops-control-plane`, confirmar o erro no log e o loop vivo; `docker start aiops-control-plane` e confirmar que a coleta volta a imprimir no stdout
- [x] 8.6 RBAC: criar um ServiceAccount sem permissões, gerar um kubeconfig com `kubectl create token`, subir a app com `KUBECONFIG` apontando para ele e confirmar a mensagem indicando a permissão `list` em `events.events.k8s.io`, com o loop vivo
- [x] 8.7 Intervalo inválido: subir com `EVENT_COLLECTION_INTERVAL_MINUTES=abc` e confirmar o warning e o uso de 3 minutos
- [x] 8.8 Shutdown: encerrar o uvicorn (Ctrl+C) durante a execução e confirmar que o loop e as tasks pendentes são cancelados sem traceback
- [x] 8.9 Registrar no PR (ou no `design.md`) o resultado de cada passo de validação, incluindo um trecho do stdout com um batch real
