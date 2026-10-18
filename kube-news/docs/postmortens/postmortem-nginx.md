# Postmortem: nginx indisponível (ImagePullBackOff)

- **Data:** 2026-10-17
- **Autor:** Fabricio Veronez
- **Status:** Resolvido
- **Severidade:** SEV3 (aplicação auxiliar indisponível em ambiente local, cluster kind)

## Resumo

O deployment `nginx`, no namespace `default`, nunca chegou a subir. Ficou cerca de 11 minutos (17:23 a 17:34 -03) em `ImagePullBackOff`, porque a imagem estava escrita `ngin` em vez de `nginx`. A correção trocou a imagem por `nginx:1.27-alpine` e acrescentou limites de recursos e verificações de saúde.

| Campo | Valor |
|---|---|
| Duração | ~11 min (horários aproximados, reconstruídos a partir da idade dos pods e dos eventos) |
| Detecção | Análise manual de saúde do cluster |
| Componentes | Deployment `default/nginx` |
| Manifesto | **Nenhum no repositório.** O deployment foi criado direto no cluster |

## Impacto

- **Disponibilidade:** 0 de 1 réplica. O nginx não tem Service, então nada dependia dele e nenhum usuário foi afetado.
- **Cluster:** mais de 20 tentativas de pull contra o Docker Hub em ~6 min, com backoff crescente. Não houve impacto nos outros workloads.
- **Dados:** nenhum, porque a aplicação não tem estado.

## Linha do tempo (-03, aproximada)

| Hora | Evento |
|---|---|
| 17:23 | Deployment `nginx` criado no namespace `default` com a imagem `ngin` |
| 17:23 | Primeiro `ErrImagePull`: `docker.io/library/ngin:latest: pull access denied, repository does not exist` |
| 17:24-17:29 | O kubelet repete o pull 5 vezes e o pod entra em `ImagePullBackOff` |
| 17:29 | A análise de saúde do cluster detecta 0/1 réplica e identifica o erro de digitação |
| 17:30 | Relatório `relatorio.md` gerado com o plano de ação |
| 17:34 | Patch aplicado no deployment pelo MCP Kubernetes. Rollout concluído (1/1) |
| 17:35 | O nginx responde com a página padrão |

## Causa raiz

A imagem do container foi escrita `ngin` (faltando o "x"). Sem registry nem tag, o runtime tentou baixar `docker.io/library/ngin:latest`, um repositório que não existe. O nome do container tinha o mesmo erro.

### Fatores que contribuíram

| Fator | Efeito |
|---|---|
| Sem tag de versão | O `:latest` implícito força `imagePullPolicy: Always` e deixa o deploy imprevisível mesmo com o nome certo |
| Sem manifesto versionado | O deployment foi criado de forma imperativa, sem revisão, e não dá para reproduzir pelo git |
| Sem resources e sem probes | QoS `BestEffort`. Mesmo funcionando, o Kubernetes não saberia se ele estava saudável |
| Namespace `default` | Fica misturado com recursos do sistema e sem isolamento |

## Resolução

Patch (merge) aplicado ao deployment `default/nginx`, substituindo o container:

| Campo | Antes | Depois |
|---|---|---|
| Nome do container | `ngin` | `nginx` |
| Imagem | `ngin` (implícito `:latest`) | `nginx:1.27-alpine` |
| `imagePullPolicy` | `Always` | `IfNotPresent` |
| Porta | — | `80` |
| Resources | nenhum | requests `25m` / `32Mi`, limits `200m` / `128Mi` |
| Readiness | nenhuma | `httpGet /` na porta 80, a cada 5s, `failureThreshold: 3` |
| Liveness | nenhuma | `httpGet /` na porta 80, delay de 5s, a cada 10s, `failureThreshold: 3` |

## Validação

| Verificação | Resultado |
|---|---|
| Rollout do deployment `nginx` concluído (1/1) | ✅ |
| Pod `Running`, pronto, 0 restarts | ✅ |
| `wget http://127.0.0.1/` dentro do pod devolve "Welcome to nginx!" | ✅ |

## Lições aprendidas

**O que funcionou bem**
- O evento do kubelet deixou o erro claro (`repository does not exist`), e o diagnóstico foi imediato.
- A falha ficou isolada: sem Service nem dependentes, nada mais foi afetado.

**O que não funcionou**
- Um recurso foi criado de forma imperativa, sem manifesto nem revisão. Um erro de digitação bastou para ele nunca subir.
- Sem tag fixa nem recursos mínimos, o deployment estaria fora do padrão mesmo com o nome certo.

**Onde tivemos sorte**
- O nginx não tinha consumidores. Uma imagem errada num serviço com dependentes teria causado indisponibilidade em cascata.

## Ações de follow-up

| Prioridade | Ação | Status |
|---|---|---|
| P1 | Decidir se o nginx deve existir no cluster. Se sim, criar `k8s/nginx.yaml` com o estado corrigido; se não, remover o deployment | Aberta |
| P2 | Se ficar, mover para um namespace próprio e criar um Service | Aberta |
| P2 | Criar uma política (Kyverno/OPA) que bloqueie imagens sem tag ou com `:latest` e containers sem `resources` | Aberta |
| P3 | Padronizar o deploy só por manifestos versionados (GitOps), proibindo `kubectl create`/`run` direto no cluster | Aberta |
