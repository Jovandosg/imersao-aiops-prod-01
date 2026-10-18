"""Pre-condicoes e preparo do cluster compartilhados pelos testes `e2e`.

Pre-requisitos (o teste e pulado com mensagem se faltar algum): contexto ativo `kind-aiops`,
PostgreSQL do docker compose, MCP Server em `MCP_SERVER_URL` e `ANTHROPIC_API_KEY` no `.env`.
Os modulos importam as fixtures `preconditions` e `scenarios` daqui.
"""

import os
import re
import subprocess
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from sqlalchemy import select

from my_agent_app.agents.analyzer import AgentConfig, RootCauseAnalyzer
from my_agent_app.agents.config import get_mcp_server_url
from my_agent_app.agents.handler import AnalysisEventHandler
from my_agent_app.collector.k8s import KubernetesEventSource
from my_agent_app.collector.transform import select_events
from my_agent_app.models.report import Report, ReportStatus

load_dotenv()

KIND_CONTEXT = "kind-aiops"
ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SCENARIOS = {"teste-a": "nginx.yaml", "teste-b": "kube-news.yaml"}
WARNING_TIMEOUT_S = 180
# Pods de um rollout em andamento podem segurar o namespace em Terminating por minutos
NAMESPACE_DELETE_TIMEOUT_S = 300


@pytest.fixture(scope="module")
def preconditions():
    try:
        _, active = config.list_kube_config_contexts()
    except Exception as exc:
        pytest.skip(f"kubeconfig indisponivel: {exc}")
    if active["name"] != KIND_CONTEXT:
        pytest.skip(f"contexto ativo e {active['name']!r}; o e2e so roda em {KIND_CONTEXT!r}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY nao definida (preencha o .env)")
    try:
        httpx.get(get_mcp_server_url(), timeout=5)
    except httpx.HTTPError as exc:
        pytest.skip(f"MCP Server nao responde em {get_mcp_server_url()} ({exc})")
    config.load_kube_config()


def _recreate_namespace(core: client.CoreV1Api, name: str) -> None:
    try:
        core.delete_namespace(name)
    except ApiException as exc:
        if exc.status != 404:
            raise
    deadline = time.monotonic() + NAMESPACE_DELETE_TIMEOUT_S
    while True:
        try:
            core.read_namespace(name)
        except ApiException as exc:
            if exc.status == 404:
                break
            raise
        if time.monotonic() > deadline:
            pytest.fail(f"namespace {name} continua Terminating apos {NAMESPACE_DELETE_TIMEOUT_S}s")
        time.sleep(2)
    core.create_namespace({"metadata": {"name": name}})


def _has_reference_warnings(raw: list[dict], namespace: str) -> bool:
    return any(e["metadata"]["namespace"] == namespace and e.get("reason") in ("Failed", "BackOff") for e in raw)


@pytest.fixture(scope="module")
def scenarios(preconditions):
    """Recria teste-a/teste-b, aplica os manifestos e espera os Warnings Failed/BackOff."""
    core = client.CoreV1Api()
    for namespace, manifest in SCENARIOS.items():
        _recreate_namespace(core, namespace)
        subprocess.run(
            ["kubectl", "--context", KIND_CONTEXT, "apply", "-n", namespace, "-f", str(ROOT / "manifestos-k8s" / manifest)],
            check=True,
            capture_output=True,
        )

    source = KubernetesEventSource()
    deadline = time.monotonic() + WARNING_TIMEOUT_S
    while True:
        raw = source._list_sync()
        if all(_has_reference_warnings(raw, ns) for ns in SCENARIOS):
            return
        if time.monotonic() > deadline:
            pytest.fail(f"Warnings Failed/BackOff de {sorted(SCENARIOS)} nao apareceram em {WARNING_TIMEOUT_S}s")
        time.sleep(5)


class CapturingAnalyzer(RootCauseAnalyzer):
    """RootCauseAnalyzer real que guarda a resposta bruta do agente."""

    responses: list[str]

    async def _persist(self, report_id, problems, text):
        self.responses.append(text)
        await super()._persist(report_id, problems, text)


async def reference_events() -> list[dict]:
    raw = await KubernetesEventSource().list()
    return [e for e in select_events(raw, watermark=None, overlap=timedelta(minutes=3)) if e["namespace"] in SCENARIOS]


async def run_analysis(sessionmaker, events: list[dict]) -> tuple[AnalysisEventHandler, CapturingAnalyzer]:
    """Analise real (handler + RootCauseAnalyzer) do lote de eventos dos cenarios."""
    analyzer = CapturingAnalyzer(sessionmaker, AgentConfig.from_env())
    analyzer.responses = []
    handler = AnalysisEventHandler(sessionmaker, analyzer, cooldown_minutes=30, stale_timeout_minutes=30)
    await handler.handle(events)
    return handler, analyzer


async def all_reports(sessionmaker) -> list[Report]:
    async with sessionmaker() as session:
        return list((await session.execute(select(Report))).scalars())


def _mentions(markdown: str, *patterns: str) -> bool:
    return any(re.search(p, markdown or "", re.IGNORECASE) for p in patterns)


def reference_reports(reports: list[Report], events: list[dict]) -> tuple[list[Report], list[Report]]:
    """Relatorios COMPLETO do nginx (teste-a, imagem) e do kube-news (teste-b, senha do banco)."""
    by_uid = {e["uid"]: e for e in events}
    complete = [r for r in reports if r.status == ReportStatus.COMPLETO]

    def pods(report):
        return {by_uid[u]["involved_object"]["name"] for u in report.event_uids if u in by_uid}

    nginx = [
        r for r in complete
        if r.namespace == "teste-a" and any(p.startswith("nginx-") for p in pods(r)) and _mentions(r.markdown, r"ngin")
    ]
    kubenews = [
        r for r in complete
        if r.namespace == "teste-b"
        and any(p.startswith("kubenews-") for p in pods(r))
        and _mentions(r.markdown, r"password", r"senha", r"autentica", r"DB_PASSWORD")
    ]
    return nginx, kubenews
