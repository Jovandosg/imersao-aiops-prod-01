import asyncio
import logging
import uuid
from typing import Protocol

logger = logging.getLogger(__name__)


class Correction(Protocol):
    async def correct(self, report_id: uuid.UUID) -> None: ...


class CorrectionExecutor:
    """Despacho fire-and-forget das correcoes, cancelaveis no shutdown (mesmo padrao do EventCollector)."""

    def __init__(self, corrector: Correction) -> None:
        self.corrector = corrector
        self._tasks: set[asyncio.Task] = set()

    def dispatch(self, report_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._run(report_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, report_id: uuid.UUID) -> None:
        try:
            await self.corrector.correct(report_id)
        except Exception:
            logger.exception("Correcao do relatorio %s falhou fora do Corrector", report_id)

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Executor de correcao encerrado (%d correcao(oes) cancelada(s))", len(tasks))
