---
adr_number: "003"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 003: PostgreSQL 18 no cluster, sem persistência

## Contexto

O kube-news usa PostgreSQL como único banco. O ambiente cloud (DOKS) é didático e descartável, e o usuário declarou que o banco fica dentro do cluster, sem volume, e que a perda de dados é aceitável.

Fatos verificados em 2026-10-18:
- O PostgreSQL 18 é a versão estável atual. O 19 está em release candidate, com GA prevista para 19/11/2026 ([postgresql.org](https://www.postgresql.org/about/news/postgresql-19-rc-1-released-3409/)).
- Pela política de 5 anos, o 18 tem suporte até ~11/2030. O 16 vai até 09/11/2028 ([endoflife.ai](https://endoflife.ai/postgresql/16)).
- No DOKS, a StorageClass padrão (`do-block-storage`) é só RWO ([DO docs](https://docs.digitalocean.com/products/kubernetes/how-to/add-volumes/index.html.md)).

## Alternativas Consideradas

- **Deployment de 1 réplica, estratégia `Recreate`, sem volume** — o mínimo que funciona e é transparente. O `Recreate` evita dois Postgres vivos ao mesmo tempo durante um update. Contra: perde todos os dados a cada restart.
- **StatefulSet com `volumeClaimTemplates`** — dados sobrevivem a restart. Contra: sem volume, não agrega nada, e com volume contraria a decisão. Além disso, `storageClassName` amarraria o manifesto ao provedor.
- **Operator (ex.: CloudNativePG)** — backup e failover. Contra: CRDs e um operador para manter, sem requisito que justifique.
- **Banco gerenciado fora do cluster** — descartado pelo usuário ("dentro de cluster Kubernetes").
- **Versões 16 e 19** — o 16 é duas versões atrás, e o 19 ainda é RC.

## Decisão

O banco é **PostgreSQL 18, dentro do cluster, sem volume**, como `Deployment` de 1 réplica com estratégia `Recreate` *(premissa — confirme ou corrija: a forma do workload foi inferida)*. Ele é exposto só por `Service` `ClusterIP` *(premissa — confirme ou corrija)*.

## Consequências

- **Positivas:** um manifesto simples, sem dependência de StorageClass do provedor (reforça o [ADR 004](004-manifesto-kubernetes-agnostico.md)). Para recomeçar do zero basta reiniciar o pod.
- **Negativas:** todo restart, reschedule ou update do pod do banco **apaga os dados e o schema**. Se o schema é criado no boot da aplicação (sync do ORM), a app fica com erro até ser reiniciada também. O procedimento operacional é "reiniciou o banco, reinicie a app" *(premissa — confirme ou corrija)*.
- **Neutras / trade-offs aceitos:**
  - backup, RPO e RTO estão fora de escopo;
  - a compatibilidade do Sequelize/`pg` com o PG 18 não é declarada explicitamente e deve ser validada na implementação;
  - no Compose de dev o banco tem volume nomeado montado em `/var/lib/postgresql` (caminho novo do PG 18). Este ADR não vale para o dev.
