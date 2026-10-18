"""Consultas e transicoes da tabela reports. O chamador controla a transacao da sessao."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from my_agent_app.models.report import Report, ReportStatus

CORRECTION_INTERRUPTED_MESSAGE = (
    "Correção interrompida (reinício da aplicação ou estagnação); "
    "ações parciais podem ter sido aplicadas no cluster"
)
CORRECTABLE_STATUSES = (ReportStatus.COMPLETO, ReportStatus.FALHA_CORRECAO)


class ProblemLike(Protocol):
    title: str
    severity: str | None
    namespace: str | None
    event_uids: list[str]
    status: str
    markdown: str


async def mark_stale(session: AsyncSession, now: datetime, stale_timeout: timedelta) -> int:
    """EM_ANALISE criado antes de `now - stale_timeout` -> INCOMPLETO."""
    result = await session.execute(
        update(Report)
        .where(Report.status == ReportStatus.EM_ANALISE, Report.created_at < now - stale_timeout)
        .values(status=ReportStatus.INCOMPLETO, updated_at=func.now())
    )
    return result.rowcount


async def find_overlapping(session: AsyncSession, uids: Sequence[str]) -> list[Report]:
    """Todos os relatorios (qualquer status) que contem algum dos uids (`&&`, indice GIN)."""
    result = await session.execute(select(Report).where(Report.event_uids.overlap(list(uids))))
    return list(result.scalars())


async def create_in_analysis(session: AsyncSession, uids: Sequence[str]) -> uuid.UUID:
    report = Report(status=ReportStatus.EM_ANALISE, event_uids=list(uids))
    session.add(report)
    await session.flush()
    return report.id


async def mark_incomplete(session: AsyncSession, report_id: uuid.UUID) -> bool:
    """EM_ANALISE -> INCOMPLETO. Retorna False se o relatorio ja saiu de EM_ANALISE."""
    result = await session.execute(
        update(Report)
        .where(Report.id == report_id, Report.status == ReportStatus.EM_ANALISE)
        .values(status=ReportStatus.INCOMPLETO, markdown=None, updated_at=func.now())
    )
    return result.rowcount > 0


async def recover_orphans(session: AsyncSession) -> int:
    """Startup: todo EM_ANALISE de uma execucao anterior -> INCOMPLETO."""
    result = await session.execute(
        update(Report)
        .where(Report.status == ReportStatus.EM_ANALISE)
        .values(status=ReportStatus.INCOMPLETO, updated_at=func.now())
    )
    return result.rowcount


def _columns(problem: ProblemLike) -> dict:
    return {
        "markdown": problem.markdown,
        "status": problem.status,
        "event_uids": list(problem.event_uids),
        "severity": problem.severity,
        "namespace": problem.namespace,
        "title": problem.title,
    }


async def swap_batch(session: AsyncSession, batch_id: uuid.UUID, problems: Sequence[ProblemLike]) -> bool:
    """O relatorio do lote vira o Problema 1 (UPDATE condicional) e os demais sao inseridos.

    Retorna False, sem inserir nada, se o lote ja saiu de EM_ANALISE.
    """
    first, *rest = problems
    result = await session.execute(
        update(Report)
        .where(Report.id == batch_id, Report.status == ReportStatus.EM_ANALISE)
        .values(**_columns(first), updated_at=func.now())
        .returning(Report.id)
    )
    if result.scalar_one_or_none() is None:
        return False
    if rest:
        await session.execute(insert(Report), [{"id": uuid.uuid4(), **_columns(p)} for p in rest])
    return True


async def list_reports(session: AsyncSession) -> list[Report]:
    """Todos os relatorios, mais recente primeiro."""
    result = await session.execute(select(Report).order_by(Report.created_at.desc()))
    return list(result.scalars())


async def get_report(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    return await session.get(Report, report_id)


async def get_status(session: AsyncSession, report_id: uuid.UUID) -> str | None:
    return await session.scalar(select(Report.status).where(Report.id == report_id))


async def start_correction(session: AsyncSession, report_id: uuid.UUID) -> bool:
    """COMPLETO/FALHA_CORRECAO -> CORRIGINDO. Retorna False se o relatorio nao estava num status acionavel."""
    result = await session.execute(
        update(Report)
        .where(Report.id == report_id, Report.status.in_(CORRECTABLE_STATUSES))
        .values(
            status=ReportStatus.CORRIGINDO,
            correction_started_at=func.now(),
            correction_result=None,
            updated_at=func.now(),
        )
        .returning(Report.id)
    )
    return result.scalar_one_or_none() is not None


async def finish_correction(session: AsyncSession, report_id: uuid.UUID, status: str, result: str) -> bool:
    """CORRIGINDO -> CORRIGIDO/FALHA_CORRECAO. Retorna False se o relatorio ja saiu de CORRIGINDO."""
    values = {"status": status, "correction_result": result, "updated_at": func.now()}
    if status == ReportStatus.CORRIGIDO:
        values["corrected_at"] = func.now()
    outcome = await session.execute(
        update(Report).where(Report.id == report_id, Report.status == ReportStatus.CORRIGINDO).values(**values)
    )
    return outcome.rowcount > 0


async def recover_correction_orphans(session: AsyncSession) -> int:
    """Startup: todo CORRIGINDO de uma execucao anterior -> FALHA_CORRECAO."""
    result = await session.execute(
        update(Report)
        .where(Report.status == ReportStatus.CORRIGINDO)
        .values(
            status=ReportStatus.FALHA_CORRECAO,
            correction_result=CORRECTION_INTERRUPTED_MESSAGE,
            updated_at=func.now(),
        )
    )
    return result.rowcount


async def mark_correction_stale(session: AsyncSession, now: datetime, limit: timedelta) -> int:
    """CORRIGINDO iniciado antes de `now - limit` -> FALHA_CORRECAO."""
    result = await session.execute(
        update(Report)
        .where(Report.status == ReportStatus.CORRIGINDO, Report.correction_started_at < now - limit)
        .values(
            status=ReportStatus.FALHA_CORRECAO,
            correction_result=CORRECTION_INTERRUPTED_MESSAGE,
            updated_at=func.now(),
        )
    )
    return result.rowcount
