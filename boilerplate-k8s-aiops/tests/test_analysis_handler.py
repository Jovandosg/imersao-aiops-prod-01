import logging
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import OperationalError

from my_agent_app.agents.handler import AnalysisEventHandler
from my_agent_app.models.report import ReportStatus

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)


def event(uid: str) -> dict:
    return {"uid": uid, "reason": "Failed", "message": "x", "timestamp": NOW.isoformat()}


@dataclass
class FakeReport:
    id: uuid.UUID
    status: str
    event_uids: list[str]
    created_at: datetime = NOW
    updated_at: datetime = NOW
    corrected_at: datetime | None = None


class FakeRepository:
    """Repositorio em memoria com a mesma interface de `models.repository`."""

    def __init__(self, reports=(), error: Exception | None = None):
        self.reports = {r.id: r for r in reports}
        self.error = error
        self.calls = []

    async def mark_stale(self, session, now, stale_timeout):
        self.calls.append("mark_stale")
        if self.error:
            raise self.error
        return 0

    async def mark_correction_stale(self, session, now, limit):
        self.calls.append(("mark_correction_stale", now, limit))
        return 0

    async def find_overlapping(self, session, uids):
        self.calls.append("find_overlapping")
        return [r for r in self.reports.values() if set(r.event_uids) & set(uids)]

    async def create_in_analysis(self, session, uids):
        self.calls.append("create_in_analysis")
        report = FakeReport(uuid.uuid4(), ReportStatus.EM_ANALISE, list(uids))
        self.reports[report.id] = report
        return report.id

    async def mark_incomplete(self, session, report_id):
        self.calls.append("mark_incomplete")
        report = self.reports[report_id]
        if report.status != ReportStatus.EM_ANALISE:
            return False
        report.status = ReportStatus.INCOMPLETO
        return True


class FakeSessionmaker:
    @asynccontextmanager
    async def begin(self):
        yield object()


@dataclass
class FakeAnalyzer:
    repository: FakeRepository
    error: Exception | None = None
    before: Callable | None = None
    calls: list = field(default_factory=list)
    seen_status: list = field(default_factory=list)

    async def analyze(self, report_id, events):
        self.calls.append((report_id, events))
        self.seen_status.append(self.repository.reports[report_id].status)
        if self.before:
            self.before(report_id)
        if self.error:
            raise self.error


def build(repository, analyzer, correction_timeout_minutes=10):
    return AnalysisEventHandler(
        FakeSessionmaker(), analyzer, cooldown_minutes=30, stale_timeout_minutes=30,
        clock=lambda: NOW, repository=repository, correction_timeout_minutes=correction_timeout_minutes,
    )


async def test_lote_inteiramente_bloqueado_nao_cria_relatorio_nem_chama_analisador():
    repo = FakeRepository([FakeReport(uuid.uuid4(), ReportStatus.COMPLETO, ["u1", "u2"])])
    analyzer = FakeAnalyzer(repo)
    await build(repo, analyzer).handle([event("u1"), event("u2")])
    assert "create_in_analysis" not in repo.calls
    assert analyzer.calls == []


async def test_analisador_recebe_so_os_liberados_e_em_analise_ja_gravado():
    repo = FakeRepository([FakeReport(uuid.uuid4(), ReportStatus.COMPLETO, ["u2"])])
    analyzer = FakeAnalyzer(repo)
    await build(repo, analyzer).handle([event("u1"), event("u2"), event("u3")])

    [(report_id, events)] = analyzer.calls
    assert [e["uid"] for e in events] == ["u1", "u3"]
    assert repo.reports[report_id].event_uids == ["u1", "u3"]
    assert analyzer.seen_status == [ReportStatus.EM_ANALISE]
    assert repo.calls[:4] == [
        "mark_stale", ("mark_correction_stale", NOW, timedelta(minutes=20)), "find_overlapping", "create_in_analysis"
    ]


async def test_falha_do_analisador_marca_incompleto(caplog):
    repo = FakeRepository()
    analyzer = FakeAnalyzer(repo, error=RuntimeError("MCP fora do ar"))
    with caplog.at_level(logging.ERROR):
        await build(repo, analyzer).handle([event("u1")])
    [(report_id, _)] = analyzer.calls
    assert repo.reports[report_id].status == ReportStatus.INCOMPLETO
    assert "MCP fora do ar" in caplog.text


async def test_falha_do_analisador_nao_sobrescreve_relatorio_ja_recuperado():
    repo = FakeRepository()

    def recovered(report_id):
        repo.reports[report_id].status = ReportStatus.INCOMPLETO

    analyzer = FakeAnalyzer(repo, error=RuntimeError("boom"), before=recovered)
    await build(repo, analyzer).handle([event("u1")])
    [(report_id, _)] = analyzer.calls
    assert repo.reports[report_id].status == ReportStatus.INCOMPLETO


async def test_banco_indisponivel_descarta_lote_sem_propagar(caplog):
    repo = FakeRepository(error=OperationalError("SELECT 1", {}, ConnectionRefusedError("recusada")))
    analyzer = FakeAnalyzer(repo)
    with caplog.at_level(logging.ERROR):
        await build(repo, analyzer).handle([event("u1")])
    assert analyzer.calls == []
    assert "Banco indisponivel" in caplog.text


async def test_log_do_lote_processado(caplog):
    repo = FakeRepository([FakeReport(uuid.uuid4(), ReportStatus.EM_ANALISE, ["u2"])])
    analyzer = FakeAnalyzer(repo)
    with caplog.at_level(logging.INFO):
        await build(repo, analyzer).handle([event("u1"), event("u2")])
    [(report_id, _)] = analyzer.calls
    assert f"2 evento(s) recebido(s), 1 bloqueado(s), relatorio {report_id}" in caplog.text


async def test_varredura_de_correcao_usa_o_dobro_do_timeout_mesmo_com_lote_bloqueado():
    repo = FakeRepository([FakeReport(uuid.uuid4(), ReportStatus.COMPLETO, ["u1"])])
    await build(repo, FakeAnalyzer(repo), correction_timeout_minutes=0.5).handle([event("u1")])
    assert ("mark_correction_stale", NOW, timedelta(minutes=1)) in repo.calls
