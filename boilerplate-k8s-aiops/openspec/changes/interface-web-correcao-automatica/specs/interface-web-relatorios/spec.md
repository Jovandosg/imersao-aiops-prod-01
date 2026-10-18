## ADDED Requirements

### Requirement: Listagem de relatórios
O sistema SHALL servir em `GET /reports` uma página HTML, renderizada com Jinja2 pela própria aplicação FastAPI, com todos os relatórios ordenados por `created_at` decrescente, sem paginação nem filtro. Cada item MUST exibir:
- o título (coluna `title`; quando nulo, "Análise em lote" seguido do ID abreviado);
- a data de criação (`created_at`);
- o status como badge;
- a severidade (coluna `severity`; quando nula, "—").

Cada item MUST ser um link para `GET /reports/{id}`. Os metadados MUST vir das colunas, nunca de parse do Markdown.

#### Scenario: Ordem por data decrescente
- **WHEN** existem relatórios criados em instantes diferentes e `GET /reports` é acessado
- **THEN** o relatório mais recente aparece primeiro

#### Scenario: Relatório sem título nem severidade
- **WHEN** a listagem contém um relatório EM_ANALISE com `title` e `severity` nulos
- **THEN** o item exibe "Análise em lote" com o ID abreviado e severidade "—"

#### Scenario: Item leva ao detalhe
- **WHEN** a listagem é renderizada
- **THEN** cada item tem link para `/reports/{id}` do respectivo relatório

#### Scenario: Banco sem relatórios
- **WHEN** a tabela `reports` está vazia e `GET /reports` é acessado
- **THEN** a página exibe "Nenhum relatório encontrado" com status 200

### Requirement: Badge de status
O status SHALL ser exibido como badge com a classe CSS do `base.html` correspondente: EM_ANALISE → `badge-processing`, COMPLETO → `badge-complete`, INCOMPLETO → `badge-incomplete`, CORRIGINDO → `badge-executing`, CORRIGIDO → `badge-executed`, FALHA_CORRECAO → `badge-execution-failed`. O mesmo mapeamento MUST ser usado na listagem e no detalhe.

#### Scenario: Cada status tem sua classe
- **WHEN** a listagem contém um relatório em cada um dos seis status
- **THEN** cada badge usa exatamente a classe mapeada para o seu status

### Requirement: Detalhe do relatório
O sistema SHALL servir em `GET /reports/{id}`, com `{id}` validado como `uuid.UUID`, uma página com o status, a severidade, o namespace, a lista de `event_uids` e o conteúdo Markdown do relatório convertido para HTML.

#### Scenario: Relatório completo
- **WHEN** um relatório COMPLETO com Markdown é acessado
- **THEN** a página exibe status, severidade, namespace, `event_uids` e o Markdown renderizado como HTML

#### Scenario: Relatório inexistente
- **WHEN** `GET /reports/{id}` é acessado com um UUID válido que não existe
- **THEN** a resposta é 404 com página informativa

#### Scenario: Id que não é UUID
- **WHEN** `GET /reports/abc` é acessado
- **THEN** a resposta é a validação do FastAPI com status 422

### Requirement: Conversão do Markdown no servidor na exibição
A conversão Markdown → HTML SHALL ser feita no servidor, com a biblioteca `markdown`, a cada requisição da página de detalhe. O banco MUST guardar apenas Markdown, nunca HTML. HTML embutido no Markdown MUST ser exibido como texto, não interpretado pelo navegador. Markdown malformado MUST seguir o comportamento nativo da biblioteca (HTML parcial, sem exceção).

#### Scenario: Tag da saída do kubectl aparece literalmente
- **WHEN** o Markdown de um relatório contém `NOMINATED NODE <none>`
- **THEN** o HTML da resposta contém `&lt;none&gt;` e o texto `<none>` aparece na página

#### Scenario: Markdown malformado
- **WHEN** o Markdown tem marcação incompleta (ex.: bloco de código sem fechamento)
- **THEN** a página é renderizada com status 200

### Requirement: Estado vazio do detalhe
Um relatório sem Markdown SHALL exibir um estado vazio explícito em vez de corpo em branco: EM_ANALISE → "Análise em andamento — atualize a página em instantes"; INCOMPLETO → "Análise não concluída — será reavaliada na próxima ocorrência dos eventos".

#### Scenario: Relatório em análise
- **WHEN** um relatório EM_ANALISE com `markdown` nulo é acessado
- **THEN** a página exibe "Análise em andamento — atualize a página em instantes"

#### Scenario: Incompleto sem conteúdo
- **WHEN** um relatório INCOMPLETO com `markdown` nulo é acessado
- **THEN** a página exibe "Análise não concluída — será reavaliada na próxima ocorrência dos eventos"

### Requirement: Banco indisponível nas páginas de relatório
Quando a consulta ao banco falhar com `SQLAlchemyError` ou `OSError`, as rotas `GET /reports` e `GET /reports/{id}` SHALL renderizar `error.html` com status 503 e a mensagem "Banco de dados indisponível, tente novamente em instantes".

#### Scenario: Erro do SQLAlchemy
- **WHEN** a consulta da listagem levanta `OperationalError`
- **THEN** a resposta é 503 com `error.html` e a mensagem de banco indisponível

#### Scenario: Conexão recusada pelo driver
- **WHEN** a consulta do detalhe levanta `ConnectionRefusedError`
- **THEN** a resposta é 503 com `error.html` e a mensagem de banco indisponível

### Requirement: Navegação para os relatórios
O cabeçalho comum (`base.html`) SHALL ter um link "Relatórios" para `/reports`, no lugar do link "Tasks". O botão de retorno do `error.html` MUST ser "Voltar para relatórios", apontando para `/reports`.

#### Scenario: Link no cabeçalho
- **WHEN** qualquer página que estende `base.html` é renderizada
- **THEN** o cabeçalho contém um link "Relatórios" para `/reports` e nenhum link "Tasks"

#### Scenario: Retorno da página de erro
- **WHEN** `error.html` é renderizado
- **THEN** o botão de retorno diz "Voltar para relatórios" e aponta para `/reports`

### Requirement: Seed de relatórios
O projeto SHALL ter um script de seed que insere relatórios em cada um dos seis status, incluindo relatórios sem Markdown (EM_ANALISE e INCOMPLETO), sem título e com `<none>` no Markdown, para validar a interface sem o agente.

#### Scenario: Seed cobre todos os status
- **WHEN** o script de seed é executado num banco migrado
- **THEN** existe ao menos um relatório em cada um dos seis status
