"""Correcao dos cenarios de referencia pela interface web: kind + PostgreSQL + MCP Server + API Anthropic.

Pre-requisitos e preparo do cluster em `tests/e2e_support.py` (pulado se o contexto ativo nao for
`kind-aiops`). Cada execucao faz uma analise e duas correcoes reais (custo na API). As correcoes
rodam em sequencia (nginx, depois kube-news) para que uma falha fique atribuivel a um cenario.
Rodar com `uv run pytest -m e2e tests/test_e2e_correcao.py`.
"""

import asyncio
import json
import time

import httpx
import pytest
from fastapi import FastAPI
from kubernetes import client

from my_agent_app.agents.correction_executor import CorrectionExecutor
from my_agent_app.agents.corrector import Corrector, CorrectorConfig
from my_agent_app.models.report import Report, ReportStatus
from my_agent_app.web.router import router as web_router
from tests.e2e_support import (  # noqa: F401  fixtures
    FIXTURES,
    all_reports,
    preconditions,
    reference_events,
    reference_reports,
    run_analysis,
    scenarios,
)

pytestmark = pytest.mark.e2e

FIXTURE = FIXTURES / "e2e_correction_responses.json"
ROLLOUT_TIMEOUT_S = 180
FIX_FORM = 'action="/reports/{id}/fix"'


class CapturingCorrector(Corrector):
    """Corrector real que guarda o resultado gravado de cada correcao."""

    results: dict

    async def _finish(self, report_id, status, result):
        self.results[report_id] = (status, result)
        await super()._finish(report_id, status, result)


def _app(sessionmaker, corrector) -> FastAPI:
    # Sem lifespan: nada de coletor nem recuperacao de orfaos durante o teste
    app = FastAPI()
    app.include_router(web_router)
    app.state.sessionmaker = sessionmaker
    app.state.correction_executor = CorrectionExecutor(corrector)
    return app


async def _get(sessionmaker, report_id) -> Report:
    async with sessionmaker() as session:
        return await session.get(Report, report_id)


async def _wait_correction(sessionmaker, report_id, timeout_s: float) -> Report:
    deadline = time.monotonic() + timeout_s
    while True:
        report = await _get(sessionmaker, report_id)
        if report.status != ReportStatus.CORRIGINDO:
            return report
        if time.monotonic() > deadline:
            pytest.fail(f"relatorio {report_id} continua CORRIGINDO apos {timeout_s:.0f}s")
        await asyncio.sleep(5)


async def _wait_until(check, description: str):
    """Espera do teste pelo rollout: o agente pode declarar CORRIGIDO com os pods ainda subindo."""
    deadline = time.monotonic() + ROLLOUT_TIMEOUT_S
    while True:
        problem = await asyncio.to_thread(check)
        if problem is None:
            return
        if time.monotonic() > deadline:
            pytest.fail(f"{description} nao ficou saudavel em {ROLLOUT_TIMEOUT_S}s: {problem}")
        await asyncio.sleep(5)


def _env(deployment, container: str) -> dict:
    [spec] = [c for c in deployment.spec.template.spec.containers if c.name == container]
    return {e.name: e.value for e in spec.env or []}


def _container(deployment, name: str):
    [spec] = [c for c in deployment.spec.template.spec.containers if c.name == name]
    return spec


def _ready_pods(namespace: str, app: str) -> list:
    pods = client.CoreV1Api().list_namespaced_pod(namespace, label_selector=f"app={app}").items
    return [
        p for p in pods
        if p.metadata.deletion_timestamp is None
        and p.status.phase == "Running"
        and all(cs.ready for cs in p.status.container_statuses or [])
        and p.status.container_statuses
    ]


def _nginx_problem() -> str | None:
    deployment = client.AppsV1Api().read_namespaced_deployment("nginx", "teste-a")
    container = _container(deployment, "nginx")
    if container.image == "ngin:latest":
        return "imagem continua ngin:latest"
    if 80 not in [p.container_port for p in container.ports or []]:
        return f"containerPort 80 perdido: {container.ports}"
    replicas = deployment.spec.replicas or 1
    if (deployment.status.available_replicas or 0) != replicas or (deployment.status.updated_replicas or 0) != replicas:
        return f"disponiveis {deployment.status.available_replicas}/{replicas}"
    if len(_ready_pods("teste-a", "nginx")) < replicas:
        return "pods nao Running/Ready"
    return None


def _kubenews_problem() -> str | None:
    apps = client.AppsV1Api()
    kubenews = apps.read_namespaced_deployment("kubenews", "teste-b")
    postgre = apps.read_namespaced_deployment("postgre", "teste-b")
    env = _env(kubenews, "kubenews")
    expected_password = _env(postgre, "postgre").get("POSTGRES_PASSWORD")
    if env.get("DB_PASSWORD") != expected_password:
        return f"DB_PASSWORD={env.get('DB_PASSWORD')!r} != POSTGRES_PASSWORD={expected_password!r}"
    # Configuracao preservada: pega o merge patch destrutivo proibido pelo prompt
    preserved = {"DB_HOST": "postgre", "DB_DATABASE": "kubenews", "DB_USERNAME": "kubenews"}
    lost = {k: env.get(k) for k, v in preserved.items() if env.get(k) != v}
    if lost:
        return f"variaveis alteradas ou removidas: {lost}"
    if _container(kubenews, "kubenews").image != "fabricioveronez/kube-news:v1":
        return f"imagem alterada: {_container(kubenews, 'kubenews').image}"
    if kubenews.spec.replicas != 10:
        return f"replicas alteradas: {kubenews.spec.replicas}"
    if (kubenews.status.available_replicas or 0) != 10 or (kubenews.status.updated_replicas or 0) != 10:
        return f"disponiveis {kubenews.status.available_replicas}/10"
    if len(_ready_pods("teste-b", "kubenews")) < 10:
        return "pods nao Running/Ready"
    return None


async def _correct(http, sessionmaker, report_id, timeout_s) -> Report:
    detail = await http.get(f"/reports/{report_id}")
    assert FIX_FORM.format(id=report_id) in detail.text

    response = await http.post(f"/reports/{report_id}/fix")
    assert response.status_code == 303
    assert response.headers["location"] == f"/reports/{report_id}"
    assert (await _get(sessionmaker, report_id)).status == ReportStatus.CORRIGINDO

    report = await _wait_correction(sessionmaker, report_id, timeout_s)
    assert report.status == ReportStatus.CORRIGIDO, f"correcao terminou {report.status}:\n{report.correction_result}"
    assert report.corrected_at is not None
    assert "Acoes Executadas" in (report.correction_result or ""), report.correction_result
    return report


async def _assert_interface_after(http, report_id):
    listing = (await http.get("/reports")).text
    item = listing[listing.index(f'href="/reports/{report_id}"'):]
    assert "badge-executed" in item[: item.index("</a>")]

    detail = (await http.get(f"/reports/{report_id}")).text
    assert "Resultado da Correção" in detail
    assert FIX_FORM.format(id=report_id) not in detail

    again = await http.post(f"/reports/{report_id}/fix")
    assert again.status_code == 303
    assert again.headers["location"] == f"/reports/{report_id}?erro=status_invalido"


async def test_correcao_dos_cenarios_de_referencia_pela_interface(scenarios, sessionmaker):
    events = await reference_events()
    assert events
    _, analyzer = await run_analysis(sessionmaker, events)
    [analysis] = analyzer.responses

    nginx, kubenews = reference_reports(await all_reports(sessionmaker), events)
    assert nginx, f"sem relatorio COMPLETO do nginx:\n{analysis}"
    assert kubenews, f"sem relatorio COMPLETO do kube-news:\n{analysis}"
    nginx_id, kubenews_id = nginx[0].id, kubenews[0].id

    corrector_config = CorrectorConfig.from_env()
    corrector = CapturingCorrector(sessionmaker, corrector_config)
    corrector.results = {}
    app = _app(sessionmaker, corrector)
    timeout_s = corrector_config.timeout_minutes * 60 + 60

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        listing = (await http.get("/reports")).text
        for report_id in (nginx_id, kubenews_id):
            item = listing[listing.index(f'href="/reports/{report_id}"'):]
            assert "badge-complete" in item[: item.index("</a>")]

        try:
            await _correct(http, sessionmaker, nginx_id, timeout_s)
            await _wait_until(_nginx_problem, "deployment nginx")
            await _assert_interface_after(http, nginx_id)

            await _correct(http, sessionmaker, kubenews_id, timeout_s)
            await _wait_until(_kubenews_problem, "deployment kubenews")
            await _assert_interface_after(http, kubenews_id)
        finally:
            await app.state.correction_executor.stop()
            _record(corrector.results, {nginx_id: "nginx", kubenews_id: "kubenews"})


def _record(results: dict, scenarios_by_id: dict) -> None:
    """Grava as respostas reais (uma vez) como casos de `tests/test_verdict.py`."""
    if FIXTURE.exists() or set(results) != set(scenarios_by_id):
        return
    cases = [
        {"scenario": scenarios_by_id[report_id], "expected": str(status), "response": result}
        for report_id, (status, result) in results.items()
    ]
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
