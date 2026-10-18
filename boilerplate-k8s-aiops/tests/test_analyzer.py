import logging
import uuid
from contextlib import asynccontextmanager

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.exc import OperationalError

from my_agent_app.agents.analyzer import AgentConfig, RootCauseAnalyzer, final_text, select_read_only
from my_agent_app.models.report import ReportStatus

CONFIG = AgentConfig(model_name="claude-haiku-4-5", max_iterations=25, mcp_server_url="http://mcp:3001/mcp")
EVENTS = [
    {"uid": "u1", "reason": "Failed", "message": "Failed to pull image ngin:latest", "timestamp": "x"},
    {"uid": "u2", "reason": "BackOff", "message": "Back-off restarting failed container", "timestamp": "x"},
]
TWO_PROBLEMS = """\
## Problema 1: Imagem inexistente
- **Severidade:** CRITICO
- **Namespace:** teste-a
- **Eventos:** u1
- **Conclusao:** conclusiva

## Problema 2: Senha do banco
- **Severidade:** ALTO
- **Namespace:** teste-b
- **Eventos:** u2
- **Conclusao:** conclusiva
"""
ALL_TOOLS = ["kubectl_get", "kubectl_describe", "kubectl_logs", "kubectl_apply", "kubectl_delete"]


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
    def __init__(self, answer):
        self.answer = answer
        self.tools = None
        self.inputs = None

    def __call__(self, tools, agent_config):
        self.tools = tools
        return self

    async def ainvoke(self, inputs):
        self.inputs = inputs
        return {"messages": [HumanMessage("prompt"), AIMessage(self.answer)]}


class FakeRepository:
    def __init__(self, applied=True, errors=0):
        self.applied = applied
        self.errors = errors
        self.calls = []

    async def swap_batch(self, session, batch_id, problems):
        return self._call("swap_batch", batch_id, problems)

    async def mark_incomplete(self, session, report_id):
        return self._call("mark_incomplete", report_id)

    def _call(self, name, *args):
        if self.errors:
            self.errors -= 1
            raise OperationalError("UPDATE", {}, ConnectionRefusedError("recusada"))
        self.calls.append((name, *args))
        return self.applied


class FakeSessionmaker:
    @asynccontextmanager
    async def begin(self):
        yield object()


async def no_sleep(seconds):
    no_sleep.calls.append(seconds)


def build(client=None, agent=None, repository=None):
    no_sleep.calls = []
    return RootCauseAnalyzer(
        FakeSessionmaker(),
        CONFIG,
        client_factory=client or FakeClient(),
        agent_factory=agent or FakeAgent(TWO_PROBLEMS),
        repository=repository or FakeRepository(),
        sleep=no_sleep,
    )


def test_select_read_only_descarta_tools_de_escrita():
    selected = select_read_only([FakeTool(n) for n in ALL_TOOLS])
    assert [t.name for t in selected] == ["kubectl_get", "kubectl_describe", "kubectl_logs"]


def test_select_read_only_avisa_tool_ausente(caplog):
    with caplog.at_level(logging.WARNING):
        selected = select_read_only([FakeTool("kubectl_get"), FakeTool("kubectl_apply")])
    assert [t.name for t in selected] == ["kubectl_get"]
    assert "kubectl_describe" in caplog.text and "kubectl_logs" in caplog.text


def test_final_text_usa_a_ultima_ai_message():
    messages = [AIMessage("pensando"), ToolMessage("saida", tool_call_id="1"), AIMessage("relatorio")]
    assert final_text(messages) == "relatorio"
    assert final_text([HumanMessage("x")]) == ""


async def test_agente_criado_so_com_tools_de_leitura_e_mcp_http():
    client, agent = FakeClient(), FakeAgent(TWO_PROBLEMS)
    await build(client=client, agent=agent).analyze(uuid.uuid4(), EVENTS)

    assert client.connections == {"k8s": {"transport": "http", "url": "http://mcp:3001/mcp"}}
    assert client.kwargs == {"handle_tool_errors": True}
    assert [t.name for t in agent.tools] == ["kubectl_get", "kubectl_describe", "kubectl_logs"]
    [message] = agent.inputs["messages"]
    assert message["role"] == "user"
    assert "u1" in message["content"] and "ngin:latest" in message["content"]


async def test_resposta_com_dois_problemas_leva_a_swap_batch():
    repo = FakeRepository()
    report_id = uuid.uuid4()
    await build(repository=repo).analyze(report_id, EVENTS)

    [(name, batch_id, problems)] = repo.calls
    assert (name, batch_id) == ("swap_batch", report_id)
    assert [(p.title, p.event_uids, p.status) for p in problems] == [
        ("Imagem inexistente", ["u1"], ReportStatus.COMPLETO),
        ("Senha do banco", ["u2"], ReportStatus.COMPLETO),
    ]


@pytest.mark.parametrize("answer", ["", "Model call limits exceeded: run limit (25/25)"])
async def test_resposta_sem_problemas_leva_a_mark_incomplete(answer):
    repo = FakeRepository()
    report_id = uuid.uuid4()
    await build(agent=FakeAgent(answer), repository=repo).analyze(report_id, EVENTS)
    assert repo.calls == [("mark_incomplete", report_id)]


async def test_falha_de_conexao_do_mcp_propaga_excecao():
    repo = FakeRepository()
    analyzer = build(client=FakeClient(error=ConnectionError("MCP fora do ar")), repository=repo)
    with pytest.raises(ConnectionError):
        await analyzer.analyze(uuid.uuid4(), EVENTS)
    assert repo.calls == []


async def test_lote_ja_recuperado_descarta_resultado_com_warning(caplog):
    with caplog.at_level(logging.WARNING):
        await build(repository=FakeRepository(applied=False)).analyze(uuid.uuid4(), EVENTS)
    assert "resultado da analise descartado" in caplog.text


async def test_gravacao_repete_com_backoff_e_tem_sucesso():
    repo = FakeRepository(errors=2)
    await build(repository=repo).analyze(uuid.uuid4(), EVENTS)
    assert [c[0] for c in repo.calls] == ["swap_batch"]
    assert no_sleep.calls == [1, 2]


async def test_gravacao_esgota_tentativas_e_loga_resposta(caplog):
    repo = FakeRepository(errors=3)
    with caplog.at_level(logging.ERROR):
        await build(repository=repo).analyze(uuid.uuid4(), EVENTS)
    assert repo.calls == []
    assert "apos 3 tentativas" in caplog.text
    assert "## Problema 1: Imagem inexistente" in caplog.text
