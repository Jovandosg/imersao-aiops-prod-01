---
prd_number: "003"
status: rascunho
priority: alta
created: 2026-06-16
issue:
depends_on: ["002"]
references: ["004"]
---

# PRD 003: Interface Web de Relatórios

## 1. Contexto

- **Sistema/produto**: Agente AIOps para Kubernetes — aplicação Python com FastAPI. O PRD 002 gera relatórios de análise de causa raiz e os persiste no PostgreSQL. Stack: Python, FastAPI, Jinja2, PostgreSQL.
- **Estado atual**: Os relatórios são gerados e armazenados no banco, mas não há forma de visualizá-los. O operador precisaria consultar o banco diretamente para acessar os resultados da análise.
- **Problema**: Sem interface de visualização, os relatórios não chegam a quem precisa agir, e o operador não consegue revisar o diagnóstico antes de decidir pela correção (PRD 004).

## 2. Solução Proposta

### Visão geral

- Interface web server-side renderizada com Jinja2 pela própria API FastAPI
- Página de listagem com todos os relatórios e seus status
- Página de detalhe com renderização do Markdown completo
- O botão "Executar correção" e a exibição do resultado da correção são entregues pelo PRD 004, sobre a página de detalhe deste PRD

### Decisões-chave

1. **Jinja2 para interface web** — Interface server-side renderizada pela própria API FastAPI, sem necessidade de frontend separado (React, Vue, etc.)
2. **Sem autenticação na v1** — Não haverá controle de acesso. Decisão aceita para simplificar a primeira entrega.
3. **Metadados lidos de colunas, não do Markdown** — Severidade, namespace e título vêm das colunas gravadas pelo PRD 002 (decisão D8 daquele PRD); a interface não faz parse do conteúdo Markdown.
4. **Depende do modelo de dados, não do agente** — Este PRD consome apenas a tabela de relatórios do Milestone 1 do PRD 002 e pode ser entregue em paralelo ao agente (Milestone 2), validado com relatórios seed.

### Fora do escopo

- **Autenticação e autorização** — Não contemplado nesta versão
- **Proteção contra prompt injection** — O conteúdo dos relatórios vem de um LLM alimentado por eventos do cluster; o projeto não trata manipulação desse conteúdo via eventos
- **Filtros avançados ou busca na listagem** — Listagem simples sem paginação ou filtro
- **Dashboard com métricas agregadas** — Apenas listagem e detalhe de relatórios
- **Botão "Executar correção", endpoint `POST /reports/{id}/fix` e seção "Resultado da Correção"** — Entregues pelo PRD 004

## 3. Funcionalidades

### US01: Listagem de relatórios

Como engenheiro de plataforma, quero acessar uma página web com a listagem de todos os relatórios de análise, para ter visibilidade do histórico de problemas investigados no cluster.

**Rules:**
- A página (`GET /reports`) exibe todos os relatórios ordenados por `created_at` decrescente (mais recente primeiro)
- Cada item da lista exibe: título (coluna `title`; ausente → "Análise em lote" com o ID abreviado), data de criação (`created_at`), status e severidade (coluna `severity`; NULL → "—")
- Cada item é clicável e leva à página de detalhe
- A página é servida pela própria API FastAPI com template Jinja2
- A listagem é alcançável a partir de qualquer página por um link "Relatórios" no cabeçalho comum (`base.html`), que substitui o link "Tasks" herdado do boilerplate
- O status é exibido como badge com mapeamento para classes CSS do `base.html`: EM_ANALISE → `badge-processing`, COMPLETO → `badge-complete`, INCOMPLETO → `badge-incomplete`, CORRIGINDO → `badge-executing`, CORRIGIDO → `badge-executed`, FALHA_CORRECAO → `badge-execution-failed`

**Edge cases:**
- Nenhum relatório no banco → exibir página com mensagem informativa ("Nenhum relatório encontrado")
- Erro de conexão com o PostgreSQL → capturar `SQLAlchemyError` e `OSError` e renderizar `error.html` com `status_code=503` e mensagem "Banco de dados indisponível, tente novamente em instantes". O `OSError` é necessário porque, com asyncpg, conexão recusada pode chegar sem ser embrulhada pelo SQLAlchemy (o PRD 002 já trata os dois no handler e no analisador)

### US02: Visualização detalhada do relatório

Como engenheiro de plataforma, quero visualizar o conteúdo completo de um relatório, para avaliar a causa raiz identificada e os passos de correção recomendados.

**Rules:**
- A página (`GET /reports/{id}`) renderiza o conteúdo Markdown completo do relatório em HTML
- A conversão Markdown → HTML é feita no servidor, com a biblioteca `markdown`, a cada exibição da página; o banco guarda apenas o Markdown, nunca HTML
- HTML embutido no Markdown é exibido como texto, e não interpretado pelo navegador (ex.: `<none>` e `<pending>` da saída do `kubectl` aparecem literalmente)
- Exibe o status atual, a severidade, o namespace e a lista de `event_uids` do relatório
- O `id` do relatório é do tipo UUID; o parâmetro `{id}` na rota é validado pelo FastAPI como `uuid.UUID`
- Relatório sem conteúdo Markdown exibe estado vazio explícito em vez de corpo em branco:
  - EM_ANALISE → "Análise em andamento — atualize a página em instantes"
  - INCOMPLETO sem Markdown → "Análise não concluída — será reavaliada na próxima ocorrência dos eventos"
- O ID de um relatório em análise permanece válido após o fim da análise: o PRD 002 converte o relatório do batch no Problema 1 (decisão D7 daquele PRD), então o refresh da página exibe o resultado em vez de 404

**Edge cases:**
- Relatório com Markdown malformado → comportamento nativo da biblioteca `markdown`: produz HTML parcial sem lançar exceção; nenhuma lógica adicional necessária
- Relatório não encontrado (UUID válido inexistente) → retornar página 404 com mensagem informativa
- `{id}` que não é UUID → resposta de validação do FastAPI (422)
- Erro de conexão com o PostgreSQL → mesmo tratamento da US01 (`error.html`, 503)

## 4. Critérios de Aceite

### Técnicos

| Critério | Método de verificação |
|----------|----------------------|
| Interface web lista todos os relatórios com título, status e severidade | Teste automatizado da rota com relatórios seed + teste manual em navegador |
| Severidade ausente é exibida como "—" | Teste automatizado com relatório EM_ANALISE (`severity` NULL) |
| Página de detalhe renderiza Markdown completo | Teste manual com relatórios de diferentes complexidades |
| HTML embutido no Markdown aparece como texto | Teste automatizado com relatório contendo `<none>`, verificando `&lt;none&gt;` no HTML da resposta |
| Relatório sem Markdown exibe estado vazio conforme o status | Teste automatizado com relatórios EM_ANALISE e INCOMPLETO sem conteúdo |
| Relatório inexistente retorna 404 | Teste automatizado com UUID inexistente |
| Banco indisponível retorna 503 com `error.html` | Teste automatizado simulando `OperationalError` e `ConnectionRefusedError` |
| Link "Relatórios" no cabeçalho leva à listagem | Teste manual em navegador |

### De negócio

Este PRD é um habilitador de visualização; não possui métrica de negócio própria na v1. O valor é viabilizar o acesso aos relatórios gerados pelo PRD 002 e servir de base para o acionamento da correção (PRD 004).

## 5. Milestones

### Milestone 1: Implementar Interface Web

**Objetivo:** Permitir visualização dos relatórios via navegador.

**Funcionalidades:** US01, US02

- [ ] Criar template Jinja2 de listagem de relatórios (US01)
- [ ] Criar rota FastAPI para listagem (`GET /reports`) usando `app.state.sessionmaker` (US01)
- [ ] Criar template Jinja2 de detalhe do relatório com renderização Markdown e estados vazios (US02)
- [ ] Criar rota FastAPI para detalhe (`GET /reports/{id: UUID}`) (US02)
- [ ] Tratar cenários de erro (banco indisponível, relatório não encontrado) (US01, US02)
- [ ] Adicionar estilos CSS para conteúdo Markdown renderizado no template de detalhe (US02)
- [ ] Substituir o link "Tasks" por "Relatórios" (`/reports`) no cabeçalho (`base.html`) e o botão "Voltar para tasks" por "Voltar para relatórios" (`/reports`) no `error.html` (US01)
- [ ] Criar seed de relatórios cobrindo todos os status para validação sem o agente (US01, US02)

**Critério de conclusão:**
- Condição: Interface web exibe listagem e detalhe dos relatórios corretamente
- Verificação: Demo em navegador com relatórios seed em todos os status; após o Milestone 2 do PRD 002, revalidar com relatórios reais
- Aprovador: Time de SRE

## 6. Riscos e Dependências

| Risco | Impacto | Mitigação | Status |
|-------|---------|-----------|--------|
| Interface sem autenticação exposta indevidamente | Médio | Restringir acesso via rede (VPN, ingress interno). Documentar que v1 não tem auth | Pendente |

**Dependências:**

| Dependência | Tipo | Status | Impacto se bloqueado |
|-------------|------|--------|----------------------|
| PRD 002 — Milestone 1 (tabela de relatórios, colunas `severity`/`namespace`/`title`, `app.state.sessionmaker`) | Interna | A implementar | Sem o modelo de dados, não há o que exibir |
| Jinja2 | Externa | Disponível | Renderização dos templates |
| Biblioteca de renderização Markdown → HTML (`markdown`) | Externa | Disponível — `markdown>=3.10.2` declarado em `pyproject.toml` | Necessária para exibir relatórios formatados |

## 7. Referências

- [PRD 002 - Agente de Análise](./002-agente-analise-causa-raiz.md) — fornece os relatórios exibidos
- [PRD 004 - Agente de Correção](./004-agente-correcao-automatica.md) — adiciona à página de detalhe o botão de correção e o resultado da correção

## 8. Registro de Decisões

- **2026-07-23** — Necessidade de um link "Relatórios" no cabeçalho (`base.html`): a listagem só era acessível digitando a URL `/reports`. *(Correção em 2026-10-18: o link não chegou ao código; o cabeçalho ainda tem "Tasks" do boilerplate. A tarefa permanece no Milestone 1.)*
- **2026-10-18** — **Link "Relatórios" substitui "Tasks"** em vez de ser adicionado ao lado: "Tasks" é sobra do boilerplate e não leva a nenhuma funcionalidade.
- **2026-10-18** — **Severidade, namespace e título lidos de colunas** gravadas pelo PRD 002 (decisão D8 daquele PRD), em vez de regex sobre o Markdown. Um único ponto de parse; relatórios sem problema exibem "—".
- **2026-10-18** — **Botão "Executar correção" movido para o PRD 004**, junto com o endpoint `POST /reports/{id}/fix`, o tratamento de conflito e a seção "Resultado da Correção". Motivo: entregue aqui, o botão apontaria para uma rota inexistente até o PRD 004; a dependência ficava invertida.
- **2026-10-18** — **Estado vazio explícito** no detalhe de relatórios sem Markdown (EM_ANALISE, INCOMPLETO de batch), antes não coberto.
- **2026-10-18** — **Entrega após o Milestone 1 do PRD 002**, em paralelo ao agente, validada com relatórios seed (decisão D14 do PRD 002).
- **2026-10-18** — **Conversão Markdown → HTML no servidor, na exibição**, com a biblioteca `markdown` já declarada; o banco guarda só Markdown. Motivo: um único formato persistido, e a renderização pode mudar sem migrar dados.
- **2026-10-18** — **HTML embutido no Markdown exibido como texto.** Motivo: correção de renderização, não segurança — o agente cola saída do `kubectl`, que contém `<none>`/`<pending>`; interpretados como tags, esses valores sumiriam da página.
- **2026-10-18** — **503 cobre `SQLAlchemyError` e `OSError`.** Motivo: só a exceção do SQLAlchemy deixaria o Postgres parado (conexão recusada no asyncpg) virar 500; mesmo conjunto que o PRD 002 já trata.
- **2026-10-18** — **`error.html` volta para a listagem de relatórios**, junto com a troca do link do cabeçalho: "Voltar para tasks" é a mesma sobra do boilerplate.
- **2026-10-18** — **Prompt injection fora do escopo do projeto.**
