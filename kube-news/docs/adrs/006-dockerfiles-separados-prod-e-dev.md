---
adr_number: "006"
status: aceito
created: 2026-10-18
supersedes: ""
superseded_by: ""
---

# ADR 006: Dockerfiles separados para produção e desenvolvimento, com Docker Compose no dev

## Contexto

O Docker tem dois papéis declarados pelo usuário: **empacotar a aplicação** para o Kubernetes e servir de **ambiente de desenvolvimento** do dia a dia. Os dois puxam para lados opostos: a imagem de produção deve ser enxuta, e o dev precisa de hot-reload e ferramentas.

Fato verificado em 2026-10-18: na imagem oficial do PostgreSQL 18, `PGDATA` passou a ser `/var/lib/postgresql/18/docker` e o volume é montado em `/var/lib/postgresql`. Montar no caminho antigo (`/var/lib/postgresql/data`) falha na subida ([Docker Hub](https://hub.docker.com/_/postgres/), [docker-library/postgres #1370](https://github.com/docker-library/postgres/issues/1370)).

## Alternativas Consideradas

- **Dois Dockerfiles: `Dockerfile` (produção) e `Dockerfile.dev` (desenvolvimento)** — cada build evolui de forma independente, e alterar um não arrisca o outro. Contra: a base comum (versão do Node, instalação de dependências) é duplicada e pode divergir.
- **Um Dockerfile multi-stage com alvos `dev` e produção** — uma única fonte, sem duplicação. Contra: os dois builds ficam acoplados no mesmo arquivo, e uma mudança para o dev pode afetar a produção.
- **Kubernetes local como dev (kind + Tilt/Skaffold)** — mais paridade com o cluster. Contra: setup pesado e loop de código mais lento.

## Decisão

- **Dois Dockerfiles** em `src/`, ambos baseados em **Node.js 24**:
  - `Dockerfile` — imagem de produção, enxuta, publicada como `fabricioveronez/kube-news-aiops` ([ADR 005](005-docker-hub-publico-com-tag-imutavel.md));
  - `Dockerfile.dev` — imagem de desenvolvimento, com hot-reload e código montado como volume.
  Motivo declarado pelo usuário: granularidade para alterar cada um quando preciso e independência entre as construções.
- O ambiente de desenvolvimento é **Docker Compose** na raiz, construindo com o `Dockerfile.dev`, com a app e o **PostgreSQL 18** *(premissa — confirme ou corrija)*.
- O Postgres do Compose usa **volume nomeado montado em `/var/lib/postgresql`** *(premissa — confirme ou corrija)*.

## Consequências

- **Positivas:** cada build muda sem risco para o outro. O `Dockerfile` de produção fica livre de qualquer coisa de dev. Cada arquivo é mais simples de ler, o que ajuda na didática. O loop de desenvolvimento é rápido, sem cluster.
- **Negativas:**
  - a base comum fica duplicada, e a versão do Node e o processo de instalação de dependências precisam ser mantidos em sincronia manualmente;
  - como o dia a dia roda o `Dockerfile.dev`, o `Dockerfile` de produção não é exercitado no desenvolvimento e precisa ser buildado e validado antes de cada deploy;
  - a paridade com o cluster é parcial: no dev o banco tem volume, no cluster não ([ADR 003](003-postgres-no-cluster-sem-persistencia.md)).
- **Neutras / trade-offs aceitos:** a configuração do Compose duplica a do manifesto. A mudança de caminho do PG 18 contradiz a maioria dos tutoriais e fica documentada como armadilha didática.
