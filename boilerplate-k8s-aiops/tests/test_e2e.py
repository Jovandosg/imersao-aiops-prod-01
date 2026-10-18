"""Fluxo completo nos cenarios de referencia: kind + PostgreSQL + MCP Server + API Anthropic.

Pre-requisitos e preparo do cluster em `tests/e2e_support.py`. Cada execucao faz uma analise
real (custo na API). Rodar com `uv run pytest -m e2e`.
"""

import json

import pytest

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

FIXTURE = FIXTURES / "e2e_agent_response.json"


async def test_fluxo_completo_diagnostica_os_cenarios_de_referencia(scenarios, sessionmaker):
    events = await reference_events()
    assert events

    handler, analyzer = await run_analysis(sessionmaker, events)

    [response] = analyzer.responses
    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(
            json.dumps({"events": events, "response": response}, ensure_ascii=False, indent=2) + "\n"
        )

    reports = await all_reports(sessionmaker)
    nginx, kubenews = reference_reports(reports, events)
    assert nginx and nginx[0].severity, f"sem relatorio COMPLETO do nginx:\n{response}"
    assert kubenews, f"sem relatorio COMPLETO do kube-news:\n{response}"

    covered = {u for r in reports for u in r.event_uids}
    by_uid = {e["uid"] for e in events}
    assert by_uid <= covered, f"uids sem relatorio: {by_uid - covered}"

    # Reentrega: os mesmos eventos nao geram nova analise
    await handler.handle(events)
    assert len(await all_reports(sessionmaker)) == len(reports)
    assert len(analyzer.responses) == 1
