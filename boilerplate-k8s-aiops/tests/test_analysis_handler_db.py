from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from my_agent_app.agents.handler import AnalysisEventHandler
from my_agent_app.models import repository
from my_agent_app.models.report import Report, ReportStatus

pytestmark = pytest.mark.db


class IncompleteAnalyzer:
    """Analise inconclusiva: finaliza o lote como INCOMPLETO, como o RootCauseAnalyzer faria."""

    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker
        self.calls = 0

    async def analyze(self, report_id, events):
        self.calls += 1
        async with self.sessionmaker.begin() as session:
            await repository.mark_incomplete(session, report_id)


class Clock:
    def __init__(self):
        self.now = datetime.now(UTC)

    def __call__(self):
        return self.now


async def test_reentrega_nao_duplica_e_cooldown_libera_nova_analise(sessionmaker):
    clock = Clock()
    analyzer = IncompleteAnalyzer(sessionmaker)
    handler = AnalysisEventHandler(sessionmaker, analyzer, cooldown_minutes=30, stale_timeout_minutes=30, clock=clock)
    events = [{"uid": u, "reason": "BackOff", "message": "x", "timestamp": clock.now.isoformat()} for u in ("u1", "u2")]

    await handler.handle(events)
    await handler.handle(events)

    async with sessionmaker() as session:
        reports = list((await session.execute(select(Report))).scalars())
    assert len(reports) == 1
    assert reports[0].status == ReportStatus.INCOMPLETO
    assert analyzer.calls == 1

    clock.now += timedelta(minutes=31)
    await handler.handle(events)

    async with sessionmaker() as session:
        reports = list((await session.execute(select(Report))).scalars())
    assert len(reports) == 2
    assert analyzer.calls == 2


async def test_lote_varre_correcoes_estagnadas_na_tx_1(sessionmaker):
    clock = Clock()
    async with sessionmaker.begin() as session:
        stale = Report(
            status=ReportStatus.CORRIGINDO, event_uids=["x1"], correction_started_at=clock.now - timedelta(minutes=21)
        )
        alive = Report(
            status=ReportStatus.CORRIGINDO, event_uids=["x2"], correction_started_at=clock.now - timedelta(minutes=19)
        )
        session.add_all([stale, alive])
    handler = AnalysisEventHandler(
        sessionmaker, IncompleteAnalyzer(sessionmaker), cooldown_minutes=30, stale_timeout_minutes=30,
        clock=clock, correction_timeout_minutes=10,
    )
    await handler.handle([{"uid": "u1", "reason": "BackOff", "message": "x", "timestamp": clock.now.isoformat()}])

    async with sessionmaker() as session:
        assert (await session.get(Report, stale.id)).status == ReportStatus.FALHA_CORRECAO
        assert (await session.get(Report, alive.id)).status == ReportStatus.CORRIGINDO
