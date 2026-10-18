## REMOVED Requirements

### Requirement: Exibição dos eventos coletados no stdout
**Reason**: O `EventHandler` placeholder, que imprimia cada lote no stdout, é substituído pelo pipeline de análise do PRD 002 (capabilities `relatorios-analise` e `agente-analise`). O contrato do handler com o coletor (`async def handle(events: list[dict]) -> None`, despacho fire-and-forget) não muda.
**Migration**: A visibilidade dos eventos passa a vir dos relatórios persistidos na tabela `reports` (`event_uids`, Markdown do diagnóstico) e da linha de log que o handler de análise registra a cada lote. O cenário de referência do nginx (`manifestos-k8s/nginx.yaml`) passa a ser verificado pelo teste ponta a ponta da capability `agente-analise`.
