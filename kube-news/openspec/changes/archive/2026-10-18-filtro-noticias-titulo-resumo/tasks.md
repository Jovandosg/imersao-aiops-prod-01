## 1. Infraestrutura de testes

- [x] 1.1 Em `src/package.json`, trocar o script `test` por `node --test test/search.test.js` e adicionar `test:integration` com `node --test test/busca.integration.test.js`, sem nenhuma dependência nova
- [x] 1.2 Criar `src/test/` e confirmar que `npm test` roda (falhando, porque o módulo ainda não existe)

## 2. Lógica da busca (`src/search.js`)

- [x] 2.1 Escrever os testes unitários de `parseTerm`: `q` ausente, vazio, só espaços, espaços nas pontas e repetidos, array (`['a','b']`), objeto (`{x:'y'}`), termo com uma e com várias palavras
- [x] 2.2 Escrever os testes unitários de `escapeLike` (`%`, `_`, `\`, combinações e a ordem do escape da barra) e de `buildWhere` (uma palavra gera um `Op.or` de `title`/`summary` com `Op.iLike`, várias palavras geram um `Op.and` desses grupos, e `content` nunca aparece)
- [x] 2.3 Implementar `parseTerm`, `escapeLike` e `buildWhere` até `npm test` passar

## 3. Rota `GET /`

- [x] 3.1 Em `src/server.js`, ler `req.query.q` com `parseTerm`. Sem palavras, manter o `findAll()` atual. Com palavras, fazer `findAll({ where: buildWhere(words) })`
- [x] 3.2 Quando há termo e o resultado vem vazio, rodar `Post.count()` para obter `hasPosts`. Nos outros casos, derivar `hasPosts` do resultado
- [x] 3.3 Renderizar `index` com `{ posts, term, hasPosts }`, onde `term` é a lista de palavras unida por um espaço

## 4. View e estilos

- [x] 4.1 Em `src/views/index.ejs`, trocar a condição da base vazia para `!hasPosts`, mantendo o bloco atual igual
- [x] 4.2 Adicionar acima do grid, fora do bloco do grid, o formulário `GET /` com `input name="q"` preenchido com `<%= term %>`, botão de buscar e o link "Limpar" para `/` só quando `term` não é vazio
- [x] 4.3 Adicionar o estado "Nenhuma notícia encontrada para "<%= term %>"" quando `hasPosts` é verdadeiro e `posts` está vazio, com o formulário visível
- [x] 4.4 Conferir que todo valor do leitor na view usa `<%= %>` e nunca `<%- %>`
- [x] 4.5 Estilizar o formulário e a mensagem em `src/static/styles/main.css`, seguindo o padrão visual existente (fontes, cores, classes no estilo BEM `posts-list__...`)

## 5. Testes de integração (app no Compose)

- [x] 5.1 Criar `src/test/busca.integration.test.js` com `BASE_URL` (padrão `http://localhost:8080`) e um prefixo aleatório por execução. As notícias de teste são criadas via `POST /api/post` no `before`
- [x] 5.2 Cobrir os cenários de correspondência: título, resumo, trecho de palavra, conteúdo ignorado, notícia aparece uma vez, várias palavras (distribuídas, faltando uma, em outra ordem)
- [x] 5.3 Cobrir caixa e acentos: "KUBERNETES" e "kubernetes" iguais, "NOTÍCIA" encontra "Notícia", "noticia" não encontra "Notícia"
- [x] 5.4 Cobrir o termo literal: `%`, `_`, `\`, aspas simples e duplas (resposta 200, só notícias que contêm o caractere)
- [x] 5.5 Cobrir a normalização e os estados da tela: `q` vazio e só espaços, espaços extras, `?q=a&q=b` e `?q[x]=y` sem erro, termo longo, campo preenchido, link "Limpar" presente só com termo, mensagem de nenhum resultado sem a de base vazia, termo com HTML escapado
- [x] 5.6 Cobrir o link: a mesma URL devolve o mesmo resultado em requisições repetidas, e uma notícia criada depois entra no resultado
- [x] 5.7 Subir o Compose e rodar `npm run test:integration` até passar

## 6. Validação manual e por ambiente

- [x] 6.1 Conferir `SHOW lc_ctype` no Postgres do Compose (`postgres:18-alpine`) e registrar o valor. Se o cenário "NOTÍCIA encontra Notícia" falhar, registrar e decidir com o usuário antes de seguir
  - Registro (2026-10-18): no PG 18 `SHOW lc_ctype` não existe mais (removido no PG 16). Via `pg_database`: `datctype=en_US.utf8`, `datcollate=en_US.utf8`, provider `libc`, encoding `UTF8`. O cenário "NOTÍCIA encontra Notícia" passou.
- [x] 6.2 Com o banco do Compose zerado, verificar que `/` e `/?q=deploy` exibem a mensagem de base vazia sem formulário, e que `/` sem notícias fica igual a hoje
- [ ] 6.3 No navegador, fazer duas buscas seguidas e conferir que voltar no navegador e "Limpar" se comportam como na spec
- [ ] 6.4 Validar a imagem de produção no kind (fluxo existente) e conferir a busca com as duas réplicas, recarregando a mesma URL várias vezes
- [ ] 6.5 No ambiente cloud, após o deploy, conferir `SHOW lc_ctype` no Postgres do cluster, rodar `npm run test:integration` com `BASE_URL` apontando para o Load Balancer, popular até 1.000 notícias via `POST /api/post` e medir o tempo de resposta de uma busca (AC12: até 1 s)
- [ ] 6.6 Marcar os critérios AC01–AC12 do PRD 001 com a evidência de cada um
