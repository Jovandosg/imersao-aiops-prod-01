from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from my_agent_app.agents.dedup import blocked_uids
from my_agent_app.models.report import ReportStatus

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
COOLDOWN = timedelta(minutes=30)


@dataclass
class FakeReport:
    status: str
    event_uids: list[str]
    created_at: datetime = NOW - timedelta(hours=1)
    updated_at: datetime = NOW - timedelta(hours=1)
    corrected_at: datetime | None = None


def event(uid: str, ts: datetime = NOW) -> dict:
    return {"uid": uid, "timestamp": ts.isoformat()}


def test_uid_sem_relatorio_e_liberado():
    assert blocked_uids([FakeReport(ReportStatus.COMPLETO, ["outro"])], [event("u1")], NOW, COOLDOWN) == set()


@pytest.mark.parametrize(
    "status",
    [ReportStatus.EM_ANALISE, ReportStatus.COMPLETO, ReportStatus.CORRIGINDO, ReportStatus.FALHA_CORRECAO],
)
def test_status_ativo_bloqueia(status):
    assert blocked_uids([FakeReport(status, ["u1"])], [event("u1")], NOW, COOLDOWN) == {"u1"}


def test_corrigido_reentrega_anterior_a_correcao_e_bloqueada():
    report = FakeReport(ReportStatus.CORRIGIDO, ["u1"], corrected_at=NOW - timedelta(minutes=5))
    assert blocked_uids([report], [event("u1", NOW - timedelta(minutes=10))], NOW, COOLDOWN) == {"u1"}


def test_corrigido_evento_no_mesmo_instante_da_correcao_e_bloqueado():
    corrected = NOW - timedelta(minutes=5)
    report = FakeReport(ReportStatus.CORRIGIDO, ["u1"], corrected_at=corrected)
    assert blocked_uids([report], [event("u1", corrected)], NOW, COOLDOWN) == {"u1"}


def test_corrigido_reincidencia_posterior_a_correcao_e_liberada():
    report = FakeReport(ReportStatus.CORRIGIDO, ["u1"], corrected_at=NOW - timedelta(minutes=5))
    assert blocked_uids([report], [event("u1", NOW)], NOW, COOLDOWN) == set()


def test_corrigido_sem_corrected_at_usa_updated_at():
    report = FakeReport(ReportStatus.CORRIGIDO, ["antes", "depois"], updated_at=NOW - timedelta(minutes=5))
    events = [event("antes", NOW - timedelta(minutes=10)), event("depois", NOW)]
    assert blocked_uids([report], events, NOW, COOLDOWN) == {"antes"}


def test_incompleto_dentro_do_cooldown_e_bloqueado():
    report = FakeReport(ReportStatus.INCOMPLETO, ["u1"], created_at=NOW - timedelta(minutes=10))
    assert blocked_uids([report], [event("u1")], NOW, COOLDOWN) == {"u1"}


def test_incompleto_fora_do_cooldown_e_liberado():
    report = FakeReport(
        ReportStatus.INCOMPLETO, ["u1"], created_at=NOW - timedelta(minutes=40), updated_at=NOW - timedelta(minutes=1)
    )
    assert blocked_uids([report], [event("u1")], NOW, COOLDOWN) == set()


def test_ativo_prevalece_sobre_antigo_liberado():
    reports = [
        FakeReport(ReportStatus.CORRIGIDO, ["u1"], corrected_at=NOW - timedelta(hours=2)),
        FakeReport(ReportStatus.EM_ANALISE, ["u1"]),
    ]
    assert blocked_uids(reports, [event("u1")], NOW, COOLDOWN) == {"u1"}


def test_lote_parcialmente_em_tratamento():
    reports = [FakeReport(ReportStatus.COMPLETO, ["u2"])]
    assert blocked_uids(reports, [event("u1"), event("u2"), event("u3")], NOW, COOLDOWN) == {"u2"}


def test_lote_inteiramente_em_tratamento():
    reports = [FakeReport(ReportStatus.COMPLETO, ["u1", "u2"]), FakeReport(ReportStatus.EM_ANALISE, ["u3"])]
    assert blocked_uids(reports, [event("u1"), event("u2"), event("u3")], NOW, COOLDOWN) == {"u1", "u2", "u3"}
