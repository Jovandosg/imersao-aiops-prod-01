## Context

A tela principal (`GET /` em `src/server.js`) faz `Post.findAll()` sem filtro nem ordem e renderiza `src/views/index.ejs`, que tem dois estados: base vazia ("Ainda não temos nenhum post") e grid de cards. O modelo `Post` (`src/models/post.js`) tem `title`, `summary`, `content` e `publishDate`, num PostgreSQL 18 acessado via Sequelize 6. O formulário de cadastro limita título a menos de 30 caracteres e resumo a menos de 50, mas `POST /api/post` não valida nada.

O projeto não tem framework de testes. O TRD deixa a estratégia de testes da aplicação em aberto. A app roda em mais de uma réplica no cluster, então o resultado não pode depender de estado da instância.

Os requisitos estão em `specs/busca-noticias/spec.md`. A motivação está em `proposal.md` e no PRD 001.

## Goals / Non-Goals

**Goals:**
- Filtrar a lista no servidor a partir de `q`, com as regras do PRD: palavras com AND, cada palavra em título OU resumo, sem diferenciar caixa, diferenciando acentos, termo literal.
- Separar a tela em três estados: base vazia, lista (filtrada ou não) e nenhum resultado.
- Manter a tela sem termo idêntica à atual.
- Deixar a lógica da busca testável sem banco, e o comportamento ponta a ponta testável contra o Postgres real.

**Non-Goals:**
- Paginação, ordenação, relevância, destaque do termo, autocompletar.
- Busca no conteúdo e busca que ignora acentos (nenhuma extensão nova do Postgres, como `unaccent`).
- Índices de busca (`pg_trgm`). O volume esperado não justifica.
- Refatorar o restante de `server.js`.

## Decisions

### 1. Lógica pura num módulo próprio (`src/search.js`)
Duas funções, sem I/O:
- `parseTerm(q)`: devolve a lista de palavras. Se `q` não for string, devolve `[]`. Faz trim, separa por `/\s+/` e descarta vazios. A lista vazia significa "sem termo".
- `buildWhere(words)`: devolve o objeto `where` do Sequelize, no formato `{ [Op.and]: words.map(w => ({ [Op.or]: [{ title: { [Op.iLike]: p } }, { summary: { [Op.iLike]: p } }] })) }`, com `p = '%' + escapeLike(w) + '%'`.

O handler de `GET /` só junta as peças. **Por quê:** o handler fica curto e as regras mais sutis (normalização, escape, AND/OR) ganham teste unitário sem precisar subir banco. **Alternativa descartada:** pôr tudo inline no handler, que só seria testável ponta a ponta.

### 2. `ILIKE` em vez de `LOWER(...) LIKE` ou busca em JavaScript
`Op.iLike` vira `ILIKE` no Postgres, que ignora caixa e preserva acentos, exatamente o que as decisões 2 e 3 do PRD pedem. **Alternativas descartadas:** `LOWER(col) LIKE LOWER(term)` é equivalente e mais verboso. Filtrar em JavaScript depois de um `findAll()` traria a tabela inteira a cada busca. Full-text search (`to_tsvector`) não casa trechos de palavra ("kube" → "Kubernetes") e aplica stemming, que o PRD não pede.

### 3. Escape dos curingas do LIKE
`escapeLike(w)` troca `\` por `\\`, depois `%` por `\%` e `_` por `\_`. A barra vem primeiro para não escapar duas vezes. O Postgres usa `\` como caractere de escape padrão do `LIKE`/`ILIKE`, então não precisa de `ESCAPE`. O Sequelize continua cuidando das aspas ao montar o literal SQL. **Por quê:** sem isso, buscar `%` ou `_` devolve todas as notícias, o que viola a decisão 5 do PRD. Como esse ponto depende de como o Sequelize monta o literal (com `standard_conforming_strings` ligado, padrão do PG 18), ele é coberto também por teste de integração, não só pelo unitário.

### 4. Contagem só quando a busca volta vazia
O handler roda o `findAll({ where })`. Se houver termo e o resultado vier vazio, roda `Post.count()` para decidir entre "nenhum resultado" e "base vazia". Sem termo, o próprio `findAll()` já diz se a base está vazia. **Por quê:** o caminho comum (lista com resultados) continua com uma única consulta. **Alternativa descartada:** contar sempre, que gasta uma consulta à toa.

A view recebe `{ posts, term, hasPosts }`. `term` é a string normalizada (palavras unidas por um espaço). `hasPosts` indica se a base tem alguma notícia.

### 5. Estados da view
```
!hasPosts                    → bloco atual de base vazia, sem formulário
hasPosts && posts.length > 0 → formulário + grid
hasPosts && posts.length = 0 → formulário + "Nenhuma notícia encontrada para "<term>""
```
O formulário fica fora do bloco do grid, acima dele. É um `<form method="GET" action="/">` com `<input name="q" value="<%= term %>">`. O link "Limpar" (`<a href="/">`) só aparece com termo aplicado. Todo valor vindo do leitor é renderizado com `<%= %>`, nunca com `<%- %>`. **Por quê do GET:** a URL carrega o estado, o que dá link compartilhável, recarregar e voltar no navegador sem código extra, e funciona em qualquer réplica.

### 6. Testes com o runner nativo do Node
O Node 24 traz `node:test`, `node:assert` e `fetch` global, então nenhuma dependência nova entra.
- **Unitários** (`src/test/search.test.js`): `parseTerm` e `buildWhere`/`escapeLike`, sem banco.
- **Integração** (`src/test/busca.integration.test.js`): fazem requisições HTTP contra a app rodando no Compose (`BASE_URL`, padrão `http://localhost:8080`). As notícias de teste são criadas via `POST /api/post` com um prefixo aleatório por execução, e as asserções procuram esse prefixo no HTML. Assim os testes funcionam com dados pré-existentes na base. O cenário de base vazia não entra aqui, porque exige banco zerado. Ele fica no checklist manual.

O script `test` do `package.json` roda só os unitários (`node --test test/search.test.js`). Um script `test:integration` roda os de integração, com a app no ar. **Alternativa descartada:** Jest ou Mocha com supertest. Exigiriam exportar o `app` de `server.js`, que hoje chama `listen` e `initDatabase` na carga, e trariam dependências novas.

## Risks / Trade-offs

- **[`ILIKE` e letras acentuadas dependem do locale do banco]** → O Compose usa `postgres:18-alpine` (musl) e o cluster usa `postgres:18` (Debian). Se o `LC_CTYPE` não for UTF-8, "NOTÍCIA" pode não casar com "Notícia". Mitigação: o cenário "Caixa ignorada em letra acentuada" é teste de integração, e uma task confere `SHOW lc_ctype` e esse cenário nos dois ambientes.
- **[Escape dependente do Sequelize]** → Se o Sequelize mexer na barra invertida ao montar o literal, o escape quebra. Mitigação: os testes de integração com `%`, `_` e `\` verificam o SQL real.
- **[Dados de teste ficam no banco de dev]** → Os testes de integração criam notícias e não apagam, porque a app não tem rota de exclusão. Mitigação: prefixo aleatório por execução. O banco de dev é descartável.
- **[Scan sequencial]** → `ILIKE '%x%'` não usa índice B-tree. Com 1.000 linhas isso custa milissegundos, e o AC12 sinaliza degradação. Se o volume crescer muito, `pg_trgm` resolve, mas fica fora do escopo.
- **[Ordem da lista continua indefinida]** → Uma mesma busca pode devolver as notícias em ordem diferente. Aceito pelo PRD.

## Migration Plan

Não há migração de dados nem de schema. O deploy é o fluxo normal: nova imagem com tag SemVer e rollout. O rollback é voltar a tag anterior. A tela sem `q` não muda, então não há impacto para quem não usa a busca.

## Open Questions

- Nenhuma que bloqueie. A verificação do AC12 (1.000 notícias no cloud) depende de popular a base do cluster, que é descartável. Uma task cobre isso via `POST /api/post`.
