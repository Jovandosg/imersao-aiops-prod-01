import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from my_agent_app.agents.config import DEFAULT_CORRECTION_TIMEOUT_MINUTES
from my_agent_app.agents.dedup import blocked_uids
from my_agent_app.models import repository as default_repository

logger = logging.getLogger(__name__)


class Analyzer(Protocol):
    """Dono da finalizacao do relatorio (troca ou INCOMPLETO); o handler so intervem em excecao."""

    async def analyze(self, report_id: uuid.UUID, events: list[dict]) -> None: ...


# Fixo e nao configuravel: a varredura nunca alcanca um agente de correcao ainda vivo
CORRECTION_STALE_FACTOR = 2


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AnalysisEventHandler:
    """Handler do coletor: deduplicacao -> relatorio EM_ANALISE -> analisador (fora da transacao)."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        analyzer: Analyzer,
        cooldown_minutes: float,
        stale_timeout_minutes: float,
        clock: Callable[[], datetime] = _utcnow,
        repository=default_repository,
        correction_timeout_minutes: float = DEFAULT_CORRECTION_TIMEOUT_MINUTES,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.analyzer = analyzer
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.stale_timeout = timedelta(minutes=stale_timeout_minutes)
        self.correction_stale_limit = timedelta(minutes=CORRECTION_STALE_FACTOR * correction_timeout_minutes)
        self.clock = clock
        self.repository = repository

    async def handle(self, events: list[dict]) -> None:
        try:
            report_id, released = await self._register(events)
        except (SQLAlchemyError, OSError) as exc:
            logger.error("Banco indisponivel na deduplicacao; lote de %d evento(s) descartado: %s", len(events), exc)
            return
        except Exception:
            logger.exception("Falha na deduplicacao; lote de %d evento(s) descartado", len(events))
            return

        logger.info(
            "Lote processado: %d evento(s) recebido(s), %d bloqueado(s), relatorio %s",
            len(events),
            len(events) - len(released),
            report_id or "nao criado",
        )
        if report_id is None:
            return

        try:
            await self.analyzer.analyze(report_id, released)
        except Exception:
            logger.exception("Analise do relatorio %s falhou; marcando INCOMPLETO", report_id)
            await self._mark_incomplete(report_id)

    async def _register(self, events: list[dict]) -> tuple[uuid.UUID | None, list[dict]]:
        """Tx 1: estagnados (analise e correcao) -> candidatos -> bloqueios -> insert EM_ANALISE, numa transacao."""
        now = self.clock()
        repo = self.repository
        async with self.sessionmaker.begin() as session:
            await repo.mark_stale(session, now, self.stale_timeout)
            await repo.mark_correction_stale(session, now, self.correction_stale_limit)
            candidates = await repo.find_overlapping(session, [e["uid"] for e in events])
            blocked = blocked_uids(candidates, events, now, self.cooldown)
            released = [e for e in events if e["uid"] not in blocked]
            if not released:
                return None, []
            report_id = await repo.create_in_analysis(session, [e["uid"] for e in released])
        return report_id, released

    async def _mark_incomplete(self, report_id: uuid.UUID) -> None:
        try:
            async with self.sessionmaker.begin() as session:
                if not await self.repository.mark_incomplete(session, report_id):
                    logger.info("Relatorio %s ja saiu de EM_ANALISE; nada a marcar", report_id)
        except Exception:
            logger.exception("Falha ao marcar o relatorio %s como INCOMPLETO", report_id)
