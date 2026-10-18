## 1. Banco e repositório de leitura

- [x] 1.1 Adicionar `correction_started_at` (timestamp com fuso, nulo) ao modelo `Report` e criar a migration Alembic `add_correction_started_at` com `downgrade`; validar `upgrade head` / `downgrade -1` contra o PostgreSQL do `docker compose` (D9)
- [x] 1.2 Implementar `repository.list_reports` (ordem `created_at` desc) e `repository.get_report` (UUID → `Report | None`) (D3)
- [x] 1.3 Testes `db`: migration adiciona a coluna nula, ordem da listagem, `get_report` inexistente

## 2. Renderização e templates base

- [x] 2.1 Implementar `web/rendering.py::render_markdown` com `fenced_code`, `tables` e a extensão `EscapeHtml` (remover `html_block` e `html`, confirmando nomes e API `deregister` na doc do Python-Markdown 3.10), devolvendo `Markup` (D2)
- [x] 2.2 Testes unitários: `<none>` vira `&lt;none&gt;`, tabela e bloco de código renderizam, Markdown malformado não levanta
- [x] 2.3 Trocar "Tasks" por "Relatórios" (`/reports`) no `base.html` e "Voltar para tasks" por "Voltar para relatórios" (`/reports`) no `error.html`

## 3. Interface web de relatórios

- [x] 3.1 Criar `templates/reports.html`: itens com título ou "Análise em lote" + ID abreviado, `created_at`, badge pelo mapeamento de status, severidade ou "—", link para o detalhe, estado vazio "Nenhum relatório encontrado"
- [x] 3.2 Criar `templates/report_detail.html`: status, severidade, namespace, `event_uids`, Markdown renderizado, estados vazios de EM_ANALISE e INCOMPLETO, estilos CSS do conteúdo Markdown
- [x] 3.3 Implementar `GET /reports` e `GET /reports/{id: uuid.UUID}` em `web/router.py` usando `app.state.sessionmaker`, com helper que converte `SQLAlchemyError`/`OSError` em `error.html` 503 e 404 em `error.html` (D3)
- [x] 3.4 Testes de rota com repositório fake: ordem, "—", "Análise em lote", vazio, badges dos seis status, detalhe completo, estados vazios, 404, 422, 503 com `OperationalError` e `ConnectionRefusedError`, link "Relatórios" no cabeçalho
- [x] 3.5 Criar `scripts/seed_reports.py` com relatórios em todos os seis status, incluindo sem Markdown, sem título e com `<none>`; documentar o comando no README

## 4. Configuração e prompts

- [x] 4.1 Adicionar a `agents/config.py`: `get_correction_model_name` (fallback `get_agent_model_name`), `get_correction_max_iterations` (padrão 25) e `get_correction_timeout_minutes` (padrão 10, fração), com warning para inválido/zero/negativo; testes no padrão de `test_agent_config.py` (D10)
- [x] 4.2 Criar `agents/correction_prompt.py` com o prompt do PRD 004 e `build_correction_prompt(markdown)`; teste de que o Markdown é injetado sem marcador remanescente
- [x] 4.3 Trocar `--type=merge` por `--type=strategic` no exemplo de `### Comando Sugerido` de `agents/prompt.py` (D11, D15 do PRD 002) e ajustar `test_prompt.py` se necessário

## 5. Veredito

- [x] 5.1 Implementar `agents/verdict.py::parse_verdict(text)` com âncora no início da linha, prefixos Markdown e ênfase tolerados, regra conservadora (qualquer `FALHA` vence) e warning sem veredito (D7)
- [x] 5.2 Testes unitários: veredito após prosa, conflitante, com `**...**`, com `-`/`#`/`>`, menção no meio de frase, resposta sem veredito, resposta vazia

## 6. Transições de correção no repositório

- [x] 6.1 Implementar `repository.start_correction` (UPDATE condicional a COMPLETO/FALHA_CORRECAO que grava `correction_started_at`, limpa `correction_result`, retorna bool) e `repository.get_status` para a escolha do conflito (D4)
- [x] 6.2 Implementar `repository.finish_correction(session, id, status, result)` condicional a CORRIGINDO, com `corrected_at=now()` só para CORRIGIDO, retornando bool (D6)
- [x] 6.3 Implementar `repository.recover_correction_orphans` e `repository.mark_correction_stale(session, now, limit)` usando `correction_started_at` e a mensagem fixa de interrupção (D8)
- [x] 6.4 Testes `db`: transição e limpeza do resultado, rejeição dos demais status, concorrência com `asyncio.gather` em sessões distintas (só uma `True`), `finish_correction` preenchendo/preservando `corrected_at` e não sobrescrevendo, órfãos, estagnação antes e depois do limite

## 7. Corrector e executor

- [x] 7.1 Implementar `agents/corrector.py::Corrector` com `CorrectorConfig.from_env()`, fábricas injetáveis, todas as tools do MCP, `ChatAnthropic(max_retries=3)` + `ModelCallLimitMiddleware(exit_behavior="end")`, `asyncio.timeout` envolvendo MCP e agente, captura de `TimeoutError` e `Exception` (não `CancelledError`), mensagens fixas e `finish_correction` com retry em `RETRYABLE_DB_ERRORS` (D6)
- [x] 7.2 Testes unitários do Corrector com fakes: CORRIGIDO grava resposta, FALHA, timeout com agente que dorme, exceção do agente, MCP fora em `get_tools`, retry da gravação, resultado descartado quando `finish_correction` retorna False, todas as tools entregues ao agente
- [x] 7.3 Implementar `agents/correction_executor.py::CorrectionExecutor` com `dispatch` (create_task + set + done callback) e `stop` (cancel + gather) (D5)
- [x] 7.4 Testes unitários do executor: `dispatch` retorna sem esperar, `stop` cancela task pendente, exceção na task não derruba o executor

## 8. Endpoint de correção e detalhe

- [x] 8.1 Implementar `POST /reports/{id}/fix`: `start_correction` em transação, `dispatch` após o commit e 303 para o detalhe; sem linha → `get_status` → 404, `?erro=em_andamento` ou `?erro=status_invalido`; banco indisponível → 503 (D4)
- [x] 8.2 Adicionar ao `report_detail.html` o formulário "Executar correção" (só COMPLETO/FALHA_CORRECAO), as mensagens de `?erro=em_andamento` e `?erro=status_invalido` e a seção "Resultado da Correção" com `render_markdown`
- [x] 8.3 Testes de rota: 303 e dispatch no sucesso, cada conflito por status, 404, 503, botão presente/ausente nos seis status, mensagens por parâmetro, seção de resultado presente/ausente

## 9. Integração no lifespan e no handler

- [x] 9.1 Em `main.py`: criar o `Corrector` e o `CorrectionExecutor` em `app.state.correction_executor`; estender `recover_orphans` para incluir `recover_correction_orphans` na mesma transação; shutdown na ordem coletor → executor → engine (D5, D8)
- [x] 9.2 Passar o timeout de correção ao `AnalysisEventHandler` e chamar `mark_correction_stale(now, 2 × timeout)` em `_register` após `mark_stale` (D8)
- [x] 9.3 Testes: lifespan recupera órfãos CORRIGINDO antes de servir e para o executor no shutdown; handler executa a varredura na Tx 1

## 10. Documentação e validação

- [x] 10.1 Documentar `CORRECTION_MODEL_NAME`, `CORRECTION_MAX_ITERATIONS` e `CORRECTION_TIMEOUT_MINUTES` em `.env.example` e na tabela do `CLAUDE.md`; atualizar a seção de arquitetura do `CLAUDE.md` com `web/`, `agents/` de correção e o executor
- [x] 10.2 Extrair de `tests/test_e2e.py` para `tests/e2e_support.py` as pré-condições, a recriação dos namespaces, o `kubectl apply` dos manifestos e a espera pelos Warnings; `test_e2e.py` continua passando (D13)
- [x] 10.3 Criar `tests/test_e2e_correcao.py` contra o cluster kind (contexto `kind-aiops`, pulado com mensagem se outro contexto estiver ativo), com `manifestos-k8s/nginx.yaml` em `teste-a` e `manifestos-k8s/kube-news.yaml` em `teste-b`: análise real dos dois cenários, app em processo com `CorrectionExecutor` real via `httpx.ASGITransport`, `GET /reports` e detalhe antes da correção, `POST /fix` do nginx e depois do kube-news, com espera até sair de CORRIGINDO (D13)
- [x] 10.4 Asserções do e2e: banco (CORRIGIDO, `corrected_at`, `correction_result`), cluster com espera de rollout (nginx: imagem corrigida, porta preservada, réplicas disponíveis; kubenews: senhas iguais, imagem/env/10 réplicas preservados, todas Ready) e interface pós-correção (`badge-executed`, resultado, botão ausente, `?erro=status_invalido`)
- [ ] 10.5 Gravar as respostas do agente de correção em `tests/fixtures/e2e_correction_responses.json` quando ausente e usá-las como casos em `tests/test_verdict.py`
- [x] 10.6 Documentar no README o roteiro do e2e de correção (pré-requisitos, comando, custo de uma análise e duas correções)
- [x] 10.7 Roteiro manual no navegador com o seed: listagem, detalhe em cada status, `<none>` literal, link "Relatórios", acionamento, conflito por clique duplo e aba antiga; registrar o resultado no `design.md`
- [ ] 10.8 Rodar `uv run pytest`, `uv run pytest -m db` e `uv run pytest -m e2e` e registrar o resultado
