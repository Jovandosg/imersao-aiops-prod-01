## Why

O PRD 002 já gera e persiste relatórios de causa raiz, mas eles só existem no banco: o operador não tem onde lê-los, e a correção continua manual (15–60 min por incidente, sujeita a erro). Esta change entrega o PRD 003 (interface web de relatórios) e o PRD 004 (agente de correção automática) juntos, porque o 004 é acionado e exibido na página de detalhe do 003 — entregues separados, um ficaria sem uso ou sem onde aparecer.

## What Changes

**Interface web (PRD 003)**
- `GET /reports`: listagem de todos os relatórios por `created_at` decrescente, com título (ou "Análise em lote" + ID abreviado), data, badge de status e severidade (NULL → "—"); estado vazio "Nenhum relatório encontrado".
- `GET /reports/{id}` (UUID): detalhe com status, severidade, namespace, `event_uids` e o Markdown convertido para HTML **no servidor, a cada exibição** (lib `markdown`); o banco guarda só Markdown. HTML embutido é exibido como texto (ex.: `<none>` do kubectl). Estados vazios explícitos para EM_ANALISE e INCOMPLETO sem Markdown.
- Erros: 404 para UUID inexistente, 422 para id inválido, 503 com `error.html` para banco indisponível (`SQLAlchemyError` e `OSError`).
- Cabeçalho: link "Tasks" vira "Relatórios"; "Voltar para tasks" do `error.html` vira "Voltar para relatórios".
- Script de seed com relatórios em todos os seis status.

**Agente de correção (PRD 004)**
- Botão "Executar correção" no detalhe, só para COMPLETO e FALHA_CORRECAO; seção "Resultado da Correção" com `correction_result`.
- `POST /reports/{id}/fix`: transição atômica para CORRIGINDO (`UPDATE` condicional), resposta `303` para o detalhe; conflito via `303` com `?erro=em_andamento` (CORRIGINDO) ou `?erro=status_invalido` (demais status); 404 para inexistente.
- Execução fora do request: `asyncio.create_task` num executor criado no `lifespan`, com cancelamento no shutdown (padrão do `EventCollector`), no lugar de `BackgroundTasks`.
- Agente LangChain com **todas** as tools do MCP (acesso irrestrito, risco aceito), `CORRECTION_MODEL_NAME` (fallback `AGENT_MODEL_NAME`), `CORRECTION_MAX_ITERATIONS` (25) e o prompt ReAct do PRD 004.
- Veredito conservador: qualquer linha `FALHA:` → FALHA_CORRECAO; CORRIGIDO só se todas as linhas de veredito forem `CORRIGIDO:`; sem veredito → FALHA_CORRECAO. `corrected_at` preenchido na transição para CORRIGIDO.
- Invariante: o relatório só sai de CORRIGINDO com o agente parado. Timeout no task (`CORRECTION_TIMEOUT_MINUTES`, 10), captura de exceção não prevista, gravação final condicional a CORRIGINDO com retry, recuperação de órfãos CORRIGINDO no startup e varredura de estagnação a 2× o timeout no ciclo do coletor.
- `correction_result` limpo ao entrar em CORRIGINDO e sempre preenchido na saída (resposta do agente ou mensagem fixa de timeout, erro ou interrupção).
- Nova coluna `correction_started_at` (migration).
- Prompt de análise: exemplo de comando sugerido passa de `--type=merge` para `--type=strategic` (decisão D15 do PRD 002).

**Fora do escopo**: autenticação, prompt injection, filtros/paginação, whitelist, dry-run, rollback, polling/JS.

## Capabilities

### New Capabilities
- `interface-web-relatorios`: listagem e detalhe de relatórios, renderização Markdown no servidor com HTML embutido escapado, estados vazios, tratamento de 404/422/503 e navegação pelo cabeçalho.
- `agente-correcao`: acionamento da correção pela página de detalhe, endpoint `/fix` com transição atômica e conflitos, executor em background, agente com acesso irrestrito via MCP, parsing do veredito, ciclo de saída de CORRIGINDO (timeout, exceção, gravação condicional, órfãos, estagnação) e `correction_result`.

### Modified Capabilities
<!-- Nenhuma: a change agente-analise-causa-raiz (relatorios-analise, agente-analise) ainda não foi arquivada, então não há spec base para delta. Os comportamentos que tocam o ciclo de status (órfãos e estagnação de CORRIGINDO, correction_started_at) ficam como requisitos novos em `agente-correcao`. -->

## Impact

- **Código**: `web/router.py` (rotas `/reports`, `/reports/{id}`, `/reports/{id}/fix`), novos templates `reports.html` e `report_detail.html`, `base.html` e `error.html`; novo pacote de correção em `agents/` (config, prompt, parser do veredito, agente, executor); `models/repository.py` (transições de correção, órfãos, estagnação); `models/report.py` (`correction_started_at`); `agents/handler.py` (varredura de CORRIGINDO na Tx 1); `agents/prompt.py` (D15); `main.py` (executor e recuperação de órfãos CORRIGINDO).
- **Banco**: nova migration Alembic com `correction_started_at`.
- **Configuração**: novas env vars `CORRECTION_MODEL_NAME`, `CORRECTION_MAX_ITERATIONS`, `CORRECTION_TIMEOUT_MINUTES` em `.env.example` e `CLAUDE.md`.
- **Cluster**: o agente de correção escreve no cluster com acesso irrestrito via MCP Server Kubernetes.
- **Custo**: chamadas adicionais à API da Anthropic por correção.
- **Pré-requisito**: arquivar `agente-analise-causa-raiz` antes de arquivar esta change, para que `openspec/specs/` contenha `relatorios-analise` e `agente-analise`.
