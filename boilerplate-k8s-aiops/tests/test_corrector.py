import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.exc import OperationalError

from my_agent_app.agents.correction_executor import CorrectionExecutor
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, ErrorData, TextContent

from my_agent_app.agents.corrector import Corrector, CorrectorConfig, tool_errors_as_results
from my_agent_app.models.report import ReportStatus

CONFIG = CorrectorConfig(
    model_name="claude-haiku-4-5", max_iterations=25, mcp_server_url="http://mcp:3001/mcp", timeout_minutes=10
)
REPORT_MARKDOWN = "# Imagem inexistente\n\n### Comando Sugerido\nkubectl patch deployment nginx"
OK_ANSWER = "Resumo em prosa.\n\nCORRIGIDO: imagem ajustada\n\n## Acoes Executadas\n- **Status:** Corrigido"
FAIL_ANSWER = "FALHA: pods em CrashLoop\n\n## Acoes Executadas\n- **Status:** Falha"
ALL_TOOLS = ["kubectl_get", "kubectl_describe", "kubectl_patch", "kubectl_scale", "kubectl_delete"]


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeClient:
    def __init__(self, tools=ALL_TOOLS, error=None):
        self.tools = [FakeTool(n) for n in tools]
        self.error = error
        self.connections = None
        self.kwargs = None

    def __call__(self, connections, **kwargs):
        self.connections = connections
        self.kwargs = kwargs
        return self

    async def get_tools(self):
        if self.error:
            raise self.error
        return self.tools


class FakeAgent:
    def __init__(self, answer=OK_ANSWER, error=None, delay=0.0):
        self.answer = answer
        self.error = error
        self.delay = delay
        self.tools = None
        self.agent_config = None
        self.inputs = None
        self.cancelled = False

    def __call__(self, tools, agent_config):
        self.tools = tools
        self.agent_config = agent_config
        return self

    async def ainvoke(self, inputs):
        self.inputs = inputs
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error:
            raise self.error
        return {"messages": [HumanMessage("prompt"), AIMessage(self.answer)]}


@dataclass
class FakeReport:
    markdown: str | None = REPORT_MARKDOWN


class FakeRepository:
    def __init__(self, report=FakeReport(), applied=True, errors=0):
        self.report = report
        self.applied = applied
        self.errors = errors
        self.finished = []

    async def get_report(self, session, report_id):
        return self.report

    async def finish_correction(self, session, report_id, status, result):
        if self.errors:
            self.errors -= 1
            raise OperationalError("UPDATE", {}, ConnectionRefusedError("recusada"))
        self.finished.append((report_id, status, result))
        return self.applied


class FakeSessionmaker:
    @asynccontextmanager
    async def __call__(self):
        yield object()

    @asynccontextmanager
    async def begin(self):
        yield object()


async def no_sleep(seconds):
    no_sleep.calls.append(seconds)


def build(client=None, agent=None, repository=None, corrector_config=CONFIG):
    no_sleep.calls = []
    return Corrector(
        FakeSessionmaker(),
        corrector_config,
        client_factory=client or FakeClient(),
        agent_factory=agent or FakeAgent(),
        repository=repository or FakeRepository(),
        sleep=no_sleep,
    )


async def test_corrigido_grava_resposta_completa():
    repo = FakeRepository()
    report_id = uuid.uuid4()
    await build(repository=repo).correct(report_id)
    assert repo.finished == [(report_id, ReportStatus.CORRIGIDO, OK_ANSWER)]


async def test_falha_grava_falha_correcao_com_resposta():
    repo = FakeRepository()
    await build(agent=FakeAgent(FAIL_ANSWER), repository=repo).correct(uuid.uuid4())
    [(_, status, result)] = repo.finished
    assert (status, result) == (ReportStatus.FALHA_CORRECAO, FAIL_ANSWER)


async def test_resposta_vazia_vira_falha_com_mensagem_fixa():
    repo = FakeRepository()
    await build(agent=FakeAgent(""), repository=repo).correct(uuid.uuid4())
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert "sem resposta" in result


async def test_todas_as_tools_e_markdown_entregues_ao_agente():
    client, agent = FakeClient(), FakeAgent()
    await build(client=client, agent=agent).correct(uuid.uuid4())
    assert client.connections == {"k8s": {"transport": "http", "url": "http://mcp:3001/mcp"}}
    assert client.kwargs == {"handle_tool_errors": True, "tool_interceptors": [tool_errors_as_results]}
    assert [t.name for t in agent.tools] == ALL_TOOLS
    assert agent.agent_config is CONFIG
    [message] = agent.inputs["messages"]
    assert REPORT_MARKDOWN in message["content"]


async def test_timeout_cancela_o_agente_antes_de_gravar(caplog):
    repo = FakeRepository()
    agent = FakeAgent(delay=10)
    fast = CorrectorConfig("m", 25, "http://mcp", timeout_minutes=0.001)  # 60 ms
    with caplog.at_level(logging.ERROR):
        await build(agent=agent, repository=repo, corrector_config=fast).correct(uuid.uuid4())
    assert agent.cancelled
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert result.startswith("Tempo limite atingido após 0.001 min;")
    assert "ações parciais podem ter sido aplicadas no cluster" in result
    assert "tempo limite" in caplog.text


async def test_mcp_lento_em_get_tools_tambem_respeita_o_timeout():
    class SlowClient(FakeClient):
        async def get_tools(self):
            await asyncio.sleep(10)

    repo = FakeRepository()
    fast = CorrectorConfig("m", 25, "http://mcp", timeout_minutes=0.001)
    await build(client=SlowClient(), repository=repo, corrector_config=fast).correct(uuid.uuid4())
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert result.startswith("Tempo limite atingido")


async def test_timeout_interno_nao_e_confundido_com_o_limite():
    repo = FakeRepository()
    await build(agent=FakeAgent(error=TimeoutError("leitura do MCP")), repository=repo).correct(uuid.uuid4())
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert result.startswith("Correção interrompida por erro: leitura do MCP;")


async def test_excecao_do_agente_vira_falha_com_mensagem(caplog):
    repo = FakeRepository()
    with caplog.at_level(logging.ERROR):
        await build(agent=FakeAgent(error=RuntimeError("API fora")), repository=repo).correct(uuid.uuid4())
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert result == "Correção interrompida por erro: API fora; ações parciais podem ter sido aplicadas no cluster"
    assert "API fora" in caplog.text


async def test_mcp_fora_em_get_tools_vira_falha():
    repo = FakeRepository()
    agent = FakeAgent()
    await build(client=FakeClient(error=ConnectionError("MCP fora do ar")), agent=agent, repository=repo).correct(
        uuid.uuid4()
    )
    [(_, status, result)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO
    assert "MCP fora do ar" in result
    assert agent.inputs is None


async def test_exception_group_do_mcp_mostra_a_causa():
    repo = FakeRepository()
    error = ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionRefusedError("conexao recusada")])
    await build(client=FakeClient(error=error), repository=repo).correct(uuid.uuid4())
    [(_, _, result)] = repo.finished
    assert result.startswith("Correção interrompida por erro: conexao recusada;")


async def test_relatorio_sem_markdown_vira_falha():
    repo = FakeRepository(report=FakeReport(markdown=None))
    await build(repository=repo).correct(uuid.uuid4())
    [(_, status, _)] = repo.finished
    assert status == ReportStatus.FALHA_CORRECAO


async def test_gravacao_repete_com_backoff():
    repo = FakeRepository(errors=2)
    await build(repository=repo).correct(uuid.uuid4())
    assert [s for _, s, _ in repo.finished] == [ReportStatus.CORRIGIDO]
    assert no_sleep.calls == [1, 2]


async def test_gravacao_esgota_tentativas_e_loga(caplog):
    repo = FakeRepository(errors=3)
    with caplog.at_level(logging.ERROR):
        await build(repository=repo).correct(uuid.uuid4())
    assert repo.finished == []
    assert "apos 3 tentativas" in caplog.text
    assert "CORRIGIDO: imagem ajustada" in caplog.text


async def test_resultado_descartado_quando_ja_saiu_de_corrigindo(caplog):
    with caplog.at_level(logging.WARNING):
        await build(repository=FakeRepository(applied=False)).correct(uuid.uuid4())
    assert "resultado da correcao descartado" in caplog.text


async def test_cancelamento_nao_grava_nada():
    repo = FakeRepository()
    task = asyncio.create_task(build(agent=FakeAgent(delay=10), repository=repo).correct(uuid.uuid4()))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.finished == []


# Interceptor de erros de tool


@dataclass
class FakeRequest:
    name: str = "kubectl_rollout"


async def test_mcp_error_da_tool_vira_resultado_de_erro(caplog):
    async def failing(request):
        raise McpError(ErrorData(code=-32603, message="Failed to execute rollout command: spawnSync kubectl ETIMEDOUT"))

    with caplog.at_level(logging.WARNING):
        result = await tool_errors_as_results(FakeRequest(), failing)
    assert isinstance(result, CallToolResult)
    assert result.isError
    [content] = result.content
    assert "kubectl_rollout" in content.text and "ETIMEDOUT" in content.text
    assert "kubectl_rollout" in caplog.text


async def test_resultado_normal_passa_intacto():
    expected = CallToolResult(content=[TextContent(type="text", text="ok")])

    async def ok(request):
        return expected

    assert await tool_errors_as_results(FakeRequest(), ok) is expected


async def test_falha_de_conexao_continua_propagando():
    async def refused(request):
        raise ConnectionRefusedError("MCP fora do ar")

    with pytest.raises(ConnectionRefusedError):
        await tool_errors_as_results(FakeRequest(), refused)


async def test_interceptor_com_tool_real_do_adaptador_gera_tool_message_de_erro():
    """Integra com o adaptador: McpError numa sessao MCP vira ToolMessage status=error, sem excecao."""
    from langchain_core.messages import ToolCall
    from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
    from mcp.types import Tool

    class FailingSession:
        async def call_tool(self, name, args, progress_callback=None):
            raise McpError(ErrorData(code=-32603, message="Failed to execute patch command"))

    tool = convert_mcp_tool_to_langchain_tool(
        FailingSession(),
        Tool(name="kubectl_patch", inputSchema={"type": "object", "properties": {}}),
        tool_interceptors=[tool_errors_as_results],
        handle_tool_errors=True,
    )
    message = await tool.ainvoke(ToolCall(name="kubectl_patch", args={}, id="call-1", type="tool_call"))
    assert message.status == "error"
    assert "Failed to execute patch command" in str(message.content)


# Executor


class FakeCorrector:
    def __init__(self, delay=0.0, error=None):
        self.delay = delay
        self.error = error
        self.started = []
        self.done = []
        self.cancelled = []

    async def correct(self, report_id):
        self.started.append(report_id)
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled.append(report_id)
            raise
        if self.error:
            raise self.error
        self.done.append(report_id)


async def test_dispatch_retorna_sem_esperar():
    corrector = FakeCorrector(delay=10)
    executor = CorrectionExecutor(corrector)
    report_id = uuid.uuid4()
    assert executor.dispatch(report_id) is None
    assert corrector.started == []
    await asyncio.sleep(0)
    assert corrector.started == [report_id]
    await executor.stop()


async def test_stop_cancela_task_pendente():
    corrector = FakeCorrector(delay=10)
    executor = CorrectionExecutor(corrector)
    report_id = uuid.uuid4()
    executor.dispatch(report_id)
    await asyncio.sleep(0)
    await executor.stop()
    assert corrector.cancelled == [report_id]
    assert corrector.done == []
    assert not executor._tasks


async def test_excecao_na_task_nao_derruba_o_executor(caplog):
    corrector = FakeCorrector(error=RuntimeError("boom"))
    executor = CorrectionExecutor(corrector)
    with caplog.at_level(logging.ERROR):
        executor.dispatch(uuid.uuid4())
        await asyncio.sleep(0.01)
    assert "boom" in caplog.text
    assert not executor._tasks

    corrector.error = None
    ok = uuid.uuid4()
    executor.dispatch(ok)
    await asyncio.sleep(0.01)
    assert corrector.done == [ok]
    await executor.stop()
