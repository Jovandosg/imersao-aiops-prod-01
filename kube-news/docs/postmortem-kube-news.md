# Postmortem: kube-news indisponível (CreateContainerConfigError)

- **Data:** 2026-10-17
- **Autor:** Fabricio Veronez
- **Status:** Resolvido
- **Severidade:** SEV2 (indisponibilidade total em ambiente local, cluster kind)

## Resumo

O kube-news ficou totalmente fora do ar por cerca de 6 minutos (17:28 a 17:34 -03), desde o deploy até a correção. O motivo foi uma referência a um Secret que não existe no manifesto.

Durante a correção apareceram mais dois defeitos que ainda não tinham se manifestado. Um faria o banco perder dados a cada restart. O outro derrubaria a aplicação assim que ela subisse, por apontar para um banco que não existe. Os três foram corrigidos no mesmo deploy.

| Campo | Valor |
|---|---|
| Duração | ~6 min (horários aproximados, reconstruídos a partir da idade dos pods e dos eventos) |
| Detecção | Análise manual de saúde do cluster |
| Componentes | Deployment `kube-news`, StatefulSet `postgres`, ConfigMap `kube-news-config` |
| Manifesto | `k8s/kube-news.yaml` |

## Impacto

Nenhum usuário real foi afetado: o ambiente é um cluster kind local, sem tráfego de produção. Nenhum dado foi perdido, porque o banco ainda não tinha nada gravado.

- **Disponibilidade:** 0 de 2 réplicas prontas. O Service NodePort `30000` ficou sem endpoints e nenhuma requisição era atendida.
- **Banco:** o `postgres-0` estava Running, mas gravava fora do PVC. Qualquer restart apagaria os dados.
- **Risco evitado:** se esse manifesto fosse para um ambiente real, o defeito do volume causaria perda silenciosa de dados. Ele só apareceria no primeiro restart do pod.

## Linha do tempo (-03, aproximada)

| Hora | Evento |
|---|---|
| 17:22 | Cluster kind criado. Nó `Ready` às 17:23 |
| 17:28 | `k8s/kube-news.yaml` aplicado. `postgres-0` sobe, mas o volume está montado em `/var/lib/postgresql/dat` |
| 17:28 | O initContainer `wait-postgres` conclui. O container `kube-news` falha com `secret "postgres" not found` (`CreateContainerConfigError`) |
| 17:29 | A análise de saúde do cluster detecta 0/2 réplicas e identifica a causa raiz |
| 17:30 | Relatório `relatorio.md` gerado com o plano de ação |
| 17:33 | Na revisão do manifesto para corrigir, aparecem dois defeitos latentes: `mountPath` e `DB_DATABASE` |
| 17:34 | Manifesto corrigido e reaplicado. Rollout do `postgres` e do `kube-news` concluídos (2/2) |
| 17:35 | Validação de ponta a ponta concluída, incluindo o teste de persistência após restart do postgres |

## Causa raiz

A causa direta foi a variável `DB_USERNAME`, que referenciava o Secret `postgres`. O Secret criado pelo próprio manifesto se chama `postgres-secret`. O `DB_PASSWORD`, logo abaixo, já usava o nome certo, então o erro era só nesse campo. Como o `secretKeyRef` não é opcional, o kubelet recusa criar o container.

```yaml
- name: DB_USERNAME
  valueFrom:
    secretKeyRef:
      name: postgres          # ← não existe; correto: postgres-secret
      key: POSTGRES_USER
```

### Defeitos latentes encontrados durante a correção

| # | Defeito | Efeito se não fosse corrigido |
|---|---|---|
| 1 | O `mountPath` do StatefulSet era `/var/lib/postgresql/dat`, mas o `PGDATA` aponta para `/var/lib/postgresql/data/pgdata` | O banco gravava na camada efêmera do container, fora do PVC. Todos os dados se perderiam a cada restart, sem nenhum erro aparente |
| 2 | O ConfigMap tinha `DB_DATABASE: vaidarruim`, mas o `POSTGRES_DB` é `kubedevnews` | Depois de corrigir o Secret, a aplicação falharia ao conectar (`database "vaidarruim" does not exist`) |

### Por que esses defeitos passaram

- O manifesto foi aplicado sem nenhuma validação estática (`kubeconform`, `--dry-run=server`). A validação de schema não pegaria nenhum dos três erros, porque todos são sintaticamente válidos.
- Os nomes que precisam bater entre si (nome do Secret, `PGDATA` com `mountPath`, `POSTGRES_DB` com `DB_DATABASE`) estão espalhados e repetidos em pontos diferentes do mesmo arquivo, sem uma fonte única.
- O defeito do volume não aparece no status do pod: o postgres fica `Running` e `Ready`. Só um teste de persistência revela o problema.

## Resolução

Todas as correções foram feitas em `k8s/kube-news.yaml` e aplicadas pelo MCP Kubernetes:

| Recurso | Antes | Depois |
|---|---|---|
| Deployment `kube-news`: `DB_USERNAME` | `secretKeyRef.name: postgres` | `postgres-secret` |
| StatefulSet `postgres`: `mountPath` | `/var/lib/postgresql/dat` | `/var/lib/postgresql/data` |
| ConfigMap `kube-news-config`: `DB_DATABASE` | `vaidarruim` | `kubedevnews` |
| Deployment `kube-news`: readiness `failureThreshold` | `1` | `3` (melhoria preventiva: uma única resposta lenta não tira mais o pod do Service) |

## Validação

| Verificação | Resultado |
|---|---|
| Rollout `kube-news` 2/2 e `postgres` 1/1, sem restarts | ✅ |
| EndpointSlice do Service `kube-news` com 2 IPs | ✅ |
| `GET /`, `/health`, `/ready` em `localhost:30000` | ✅ HTTP 200 |
| Logs mostram o sync do Sequelize na base `kubedevnews` | ✅ |
| `POST /post` cria o post, que aparece na listagem | ✅ HTTP 302 |
| Post continua na listagem depois de `rollout restart` do StatefulSet `postgres` | ✅ Persistência confirmada |

## Lições aprendidas

**O que funcionou bem**
- O initContainer `wait-postgres` isolou bem o problema: ficou claro na hora que o banco estava acessível e que a falha era de configuração do container.
- A mensagem do kubelet (`secret "postgres" not found`) apontou direto para a causa.
- O teste de persistência com restart do banco confirmou que a correção do volume funcionou, sem depender do status `Running`.

**O que não funcionou**
- Três erros de configuração no mesmo manifesto chegaram ao cluster sem nenhuma revisão ou validação automática.
- O status dos pods escondia um defeito grave (o do volume). "Running" não significa "saudável".

**Onde tivemos sorte**
- O defeito do volume foi encontrado antes de existir qualquer dado no banco. Num ambiente com dados, o primeiro restart do postgres teria apagado tudo.

## Ações de follow-up

| Prioridade | Ação | Status |
|---|---|---|
| P1 | Adicionar ao fluxo de deploy um teste de persistência (gravar, reiniciar o postgres, ler) | Aberta |
| P1 | Validar o manifesto antes de aplicar: `kubectl apply --dry-run=server` + `kubeconform` | Aberta |
| P2 | Fazer o Secret `postgres-secret` ser a única fonte de credenciais e nome do banco (ex.: `DB_DATABASE` vindo de `POSTGRES_DB` via `secretKeyRef`), eliminando a duplicação com o ConfigMap | Aberta |
| P2 | Criar uma política (Kyverno/OPA) ou um check de CI que confira se `mountPath` contém o `PGDATA` | Aberta |
| P3 | Remover a senha em texto puro de `k8s/kube-news.yaml` e usar Sealed Secrets ou External Secrets | Aberta |
| P3 | Apagar o post de teste "Teste persistencia" criado durante a validação | Aberta |
