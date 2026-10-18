import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, TextContent
from sqlalchemy.ext.asyncio import async_sessionmaker

from my_agent_app.agents import config
from my_agent_app.agents.analyzer import PERSIST_ATTEMPTS, RETRYABLE_DB_ERRORS, build_agent, final_text
from my_agent_app.agents.correction_prompt import build_correction_prompt
from my_agent_app.agents.verdict import parse_verdict
from my_agent_app.models import repository as default_repository
from my_agent_app.models.report import ReportStatus

logger = logging.getLogger(__name__)

PARTIAL_ACTIONS = "ações parciais podem ter sido aplicadas no cluster"
EMPTY_RESPONSE_MESSAGE = f"Agente de correção terminou sem resposta; {PARTIAL_ACTIONS}"


def timeout_message(minutes: float) -> str:
    return f"Tempo limite atingido após {minutes:g} min; {PARTIAL_ACTIONS} — verifique antes de tentar novamente"


def _describe(exc: BaseException) -> str:
    # O cliente MCP levanta ExceptionGroup ("unhandled errors in a TaskGroup"): mostra as causas
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe(e) for e in exc.exceptions)
    return str(exc) or type(exc).__name__


def error_message(exc: BaseException) -> str:
    return f"Correção interrompida por erro: {_describe(exc)}; {PARTIAL_ACTIONS}"


async def tool_errors_as_results(
    request: MCPToolCallRequest, handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]]
) -> MCPToolCallResult:
    """Erro de execucao de uma tool vira resultado `isError` para o agente reagir, em vez de abortar a correcao.

    O MCP Server Kubernetes sinaliza falhas do kubectl com erro JSON-RPC (`McpError`), que o
    `handle_tool_errors` do adaptador nao cobre. Falhas de conexao/transporte continuam propagando.
    """
    try:
        return await handler(request)
    except McpError as exc:
        logger.warning("Tool %s falhou; erro devolvido ao agente: %s", request.name, exc)
        return CallToolResult(isError=True, content=[TextContent(type="text", text=f"Erro na tool {request.name}: {exc}")])


@dataclass(frozen=True)
class CorrectorConfig:
    model_name: str
    max_iterations: int
    mcp_server_url: str
    timeout_minutes: float

    @classmethod
    def from_env(cls) -> "CorrectorConfig":
        return cls(
            config.get_correction_model_name(),
            config.get_correction_max_iterations(),
            config.get_mcp_server_url(),
            config.get_correction_timeout_minutes(),
        )


class Corrector:
    """MCP (todas as tools) -> agente -> veredito -> saida condicional de CORRIGINDO.

    Tudo o que toca o MCP ou o agente roda sob o timeout: ao estourar, a coroutine e cancelada
    antes da gravacao, entao o relatorio so sai de CORRIGINDO com o agente parado.
    CancelledError (shutdown) nao e capturada: o relatorio fica CORRIGINDO para a recuperacao do startup.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        corrector_config: CorrectorConfig,
        client_factory: Callable = MultiServerMCPClient,
        agent_factory: Callable = build_agent,
        repository=default_repository,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.config = corrector_config
        self.client_factory = client_factory
        self.agent_factory = agent_factory
        self.repository = repository
        self.sleep = sleep

    async def correct(self, report_id: uuid.UUID) -> None:
        started = time.monotonic()
        timeout = asyncio.timeout(self.config.timeout_minutes * 60)
        try:
            markdown = await self._load_markdown(report_id)
            async with timeout:
                text = await self._run_agent(markdown)
            status = parse_verdict(text)
            result = text if text.strip() else EMPTY_RESPONSE_MESSAGE
        except TimeoutError as exc:
            if not timeout.expired():
                logger.exception("Correcao do relatorio %s falhou", report_id)
                status, result = ReportStatus.FALHA_CORRECAO, error_message(exc)
            else:
                logger.error(
                    "Correcao do relatorio %s cancelada por tempo limite (%g min)", report_id, self.config.timeout_minutes
                )
                status, result = ReportStatus.FALHA_CORRECAO, timeout_message(self.config.timeout_minutes)
        except Exception as exc:
            logger.exception("Correcao do relatorio %s falhou", report_id)
            status, result = ReportStatus.FALHA_CORRECAO, error_message(exc)

        logger.info("Correcao do relatorio %s terminou em %.1fs: %s", report_id, time.monotonic() - started, status)
        await self._finish(report_id, status, result)

    async def _load_markdown(self, report_id: uuid.UUID) -> str:
        async with self.sessionmaker() as session:
            report = await self.repository.get_report(session, report_id)
        if report is None or not report.markdown:
            raise ValueError(f"relatório {report_id} sem conteúdo para corrigir")
        return report.markdown

    async def _run_agent(self, markdown: str) -> str:
        client = self.client_factory(
            {"k8s": {"transport": "http", "url": self.config.mcp_server_url}},
            handle_tool_errors=True,
            tool_interceptors=[tool_errors_as_results],
        )
        tools = await client.get_tools()
        agent = self.agent_factory(tools, self.config)
        result = await agent.ainvoke({"messages": [{"role": "user", "content": build_correction_prompt(markdown)}]})
        return final_text(result["messages"])

    async def _finish(self, report_id: uuid.UUID, status: str, result: str) -> None:
        for attempt in range(1, PERSIST_ATTEMPTS + 1):
            try:
                async with self.sessionmaker.begin() as session:
                    applied = await self.repository.finish_correction(session, report_id, status, result)
            except RETRYABLE_DB_ERRORS as exc:
                if attempt == PERSIST_ATTEMPTS:
                    logger.error(
                        "Falha ao gravar a correcao do relatorio %s apos %d tentativas (a varredura de estagnacao "
                        "cobre): %s\nResultado:\n%s",
                        report_id,
                        PERSIST_ATTEMPTS,
                        exc,
                        result,
                    )
                    return
                await self.sleep(2 ** (attempt - 1))
                continue

            if not applied:
                logger.warning("Relatorio %s ja saiu de CORRIGINDO; resultado da correcao descartado", report_id)
            return
