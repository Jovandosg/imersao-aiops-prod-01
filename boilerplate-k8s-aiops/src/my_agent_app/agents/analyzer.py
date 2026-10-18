import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from my_agent_app.agents import config
from my_agent_app.agents.parser import Problem, parse_report
from my_agent_app.agents.prompt import build_prompt
from my_agent_app.models import repository as default_repository

logger = logging.getLogger(__name__)

READ_ONLY_TOOLS = ("kubectl_get", "kubectl_describe", "kubectl_logs")
PERSIST_ATTEMPTS = 3
RETRYABLE_DB_ERRORS = (OperationalError, InterfaceError, OSError)


@dataclass(frozen=True)
class AgentConfig:
    model_name: str
    max_iterations: int
    mcp_server_url: str

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(config.get_agent_model_name(), config.get_agent_max_iterations(), config.get_mcp_server_url())


def select_read_only(tools: Sequence[BaseTool]) -> list[BaseTool]:
    """Mantem so as tools de leitura; qualquer outra tool do MCP Server e descartada."""
    selected = [t for t in tools if t.name in READ_ONLY_TOOLS]
    missing = set(READ_ONLY_TOOLS) - {t.name for t in selected}
    if missing:
        logger.warning("MCP Server nao expoe as tools %s; seguindo com as disponiveis", ", ".join(sorted(missing)))
    return selected


def build_agent(tools: Sequence[BaseTool], agent_config: AgentConfig):
    model = ChatAnthropic(model=agent_config.model_name, max_retries=3)
    return create_agent(
        model,
        tools,
        middleware=[ModelCallLimitMiddleware(run_limit=agent_config.max_iterations, exit_behavior="end")],
    )


def final_text(messages: Sequence) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.text
    return ""


class RootCauseAnalyzer:
    """MCP -> tools somente leitura -> agente -> parse -> troca do lote (ou INCOMPLETO).

    Cliente MCP e agente sao criados a cada analise: MCP fora do ar vira excecao aqui
    (o handler marca INCOMPLETO) e um MCP reiniciado volta a funcionar sem reiniciar a app.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        agent_config: AgentConfig,
        client_factory: Callable = MultiServerMCPClient,
        agent_factory: Callable = build_agent,
        repository=default_repository,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.config = agent_config
        self.client_factory = client_factory
        self.agent_factory = agent_factory
        self.repository = repository
        self.sleep = sleep

    async def analyze(self, report_id: uuid.UUID, events: list[dict]) -> None:
        started = time.monotonic()
        client = self.client_factory(
            {"k8s": {"transport": "http", "url": self.config.mcp_server_url}},
            handle_tool_errors=True,
        )
        tools = select_read_only(await client.get_tools())
        agent = self.agent_factory(tools, self.config)
        result = await agent.ainvoke({"messages": [{"role": "user", "content": build_prompt(events)}]})

        text = final_text(result["messages"])
        problems = parse_report(text, [e["uid"] for e in events])
        logger.info(
            "Analise do relatorio %s concluida em %.1fs: %d problema(s)",
            report_id,
            time.monotonic() - started,
            len(problems),
        )
        await self._persist(report_id, problems, text)

    async def _persist(self, report_id: uuid.UUID, problems: list[Problem], text: str) -> None:
        for attempt in range(1, PERSIST_ATTEMPTS + 1):
            try:
                async with self.sessionmaker.begin() as session:
                    if problems:
                        applied = await self.repository.swap_batch(session, report_id, problems)
                    else:
                        applied = await self.repository.mark_incomplete(session, report_id)
            except RETRYABLE_DB_ERRORS as exc:
                if attempt == PERSIST_ATTEMPTS:
                    logger.error(
                        "Falha ao gravar o resultado do relatorio %s apos %d tentativas: %s\nResposta do agente:\n%s",
                        report_id,
                        PERSIST_ATTEMPTS,
                        exc,
                        text,
                    )
                    return
                await self.sleep(2 ** (attempt - 1))
                continue

            if not applied:
                logger.warning("Relatorio %s ja saiu de EM_ANALISE; resultado da analise descartado", report_id)
            elif not problems:
                logger.warning("Resposta do agente sem problemas identificaveis; relatorio %s INCOMPLETO", report_id)
            return
