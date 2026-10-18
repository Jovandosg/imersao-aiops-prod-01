from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Protocol

from my_agent_app.models.report import ReportStatus

ACTIVE_STATUSES = {
    ReportStatus.EM_ANALISE,
    ReportStatus.COMPLETO,
    ReportStatus.CORRIGINDO,
    ReportStatus.FALHA_CORRECAO,
}


class ReportLike(Protocol):
    status: str
    event_uids: list[str]
    created_at: datetime
    updated_at: datetime
    corrected_at: datetime | None


def _blocks(report: ReportLike, event_ts: datetime, now: datetime, cooldown: timedelta) -> bool:
    if report.status in ACTIVE_STATUSES:
        return True
    if report.status == ReportStatus.CORRIGIDO:
        # So libera evento estritamente posterior: o mesmo instante da correcao conta como reentrega
        return event_ts <= (report.corrected_at or report.updated_at)
    if report.status == ReportStatus.INCOMPLETO:
        return report.created_at > now - cooldown
    return False


def blocked_uids(
    reports: Iterable[ReportLike],
    events: list[dict],
    now: datetime,
    cooldown: timedelta,
) -> set[str]:
    """Uids do lote bloqueados por algum relatorio que os contem (nunca so o mais recente)."""
    reports = list(reports)
    blocked = set()
    for event in events:
        uid = event["uid"]
        event_ts = datetime.fromisoformat(event["timestamp"])
        if any(uid in r.event_uids and _blocks(r, event_ts, now, cooldown) for r in reports):
            blocked.add(uid)
    return blocked
