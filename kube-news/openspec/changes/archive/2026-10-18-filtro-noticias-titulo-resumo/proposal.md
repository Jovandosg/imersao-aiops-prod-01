## Why

A tela principal do Kube-News lista todas as notícias sem nenhuma forma de busca. Com o aumento da base, o leitor que procura uma notícia específica precisa percorrer a lista inteira. Origem: [PRD 001](../../../docs/prds/001-filtro-noticias-titulo-resumo.md).

## What Changes

- A rota `GET /` passa a aceitar o parâmetro `q`. Com um termo, a lista mostra só as notícias em que todas as palavras do termo aparecem no título ou no resumo, sem diferenciar maiúsculas e minúsculas, diferenciando acentos e tratando o termo de forma literal.
- `index.ejs` ganha um formulário de busca (GET) acima da lista. O campo continua preenchido com o termo aplicado, e há um link "Limpar" quando existe termo.
- A tela ganha um estado novo, "nenhuma notícia encontrada para [termo]", diferente do estado de base vazia. Na base vazia o campo de busca não aparece e a mensagem atual prevalece, mesmo com `q` na URL.
- Sem termo (ou com termo só de espaços), a tela se comporta exatamente como hoje.

Fora do escopo, conforme o PRD: paginação, ordenação, busca no conteúdo, busca que ignora acentos, relevância e destaque, outros filtros, autocompletar.

## Capabilities

### New Capabilities
- `busca-noticias`: busca de notícias por termo no título e no resumo na tela principal, incluindo a normalização do termo, as regras de correspondência, os estados da tela e o resultado acessível por link.

### Modified Capabilities
<!-- Nenhuma: as specs existentes (container-image, dev-environment, kubernetes-manifest, local-validation) tratam de infraestrutura e não mudam. -->

## Impact

- `src/server.js`: handler de `GET /` (leitura e normalização de `q`, montagem do filtro, contagem de posts quando a busca volta vazia).
- `src/views/index.ejs`: formulário de busca, link "Limpar" e o novo estado sem resultado.
- `src/static/styles/main.css`: estilos do formulário e da mensagem.
- `src/package.json`: o script `test` passa a rodar os testes com o runner nativo do Node (`node --test`), sem nenhuma dependência nova. Hoje o projeto não tem nenhuma infraestrutura de testes.
- Novo módulo em `src/` com a lógica pura da busca, e testes em `src/test/`.
- Banco: sem mudança de schema e sem extensão nova do Postgres. A correspondência usa `ILIKE` via `Op.iLike` do Sequelize.
- Nenhuma mudança na API, nas rotas de cadastro ou nos manifestos.
