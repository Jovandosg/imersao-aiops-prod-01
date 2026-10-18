import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from my_agent_app.collector.transform import select_events

logger = logging.getLogger(__name__)

RBAC_HINT = (
    "permissao necessaria: verbo 'list' no recurso 'events' do grupo "
    "'events.k8s.io' (events.events.k8s.io) em todos os namespaces"
)


class EventSource(Protocol):
    async def list(self) -> list[dict]: ...


class Handler(Protocol):
    async def handle(self, events: list[dict]) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EventCollector:
    """Ciclo coletar -> despachar -> dormir, com marca d'agua em memoria."""

    def __init__(
        self,
        source: EventSource,
        handler: Handler,
        interval_minutes: float,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.source = source
        self.handler = handler
        self.interval = timedelta(minutes=interval_minutes)
        self.clock = clock
        self.watermark: datetime | None = None
        self._handler_tasks: set[asyncio.Task] = set()
        self._loop_task: asyncio.Task | None = None

    async def collect_once(self) -> None:
        started_at = self.clock()
        try:
            raw_events = await self.source.list()
        except ApiException as exc:
            if exc.status in (401, 403):
                logger.error("Coleta de eventos negada (HTTP %s): %s", exc.status, RBAC_HINT)
            else:
                logger.error("Erro da API Kubernetes na coleta de eventos (HTTP %s): %s", exc.status, exc.reason)
            return
        except (HTTPError, OSError) as exc:
            logger.error("Falha ao coletar eventos: cluster inacessivel (%s); nova tentativa no proximo ciclo", exc)
            return
        except Exception:
            logger.exception("Falha ao coletar eventos do cluster; nova tentativa no proximo ciclo")
            return

        events = select_events(raw_events, self.watermark, self.interval)
        self.watermark = started_at

        if events:
            self._dispatch(events)

    def _dispatch(self, events: list[dict]) -> None:
        task = asyncio.create_task(self._run_handler(events))
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_tasks.discard)

    async def _run_handler(self, events: list[dict]) -> None:
        try:
            await self.handler.handle(events)
        except Exception:
            logger.exception("EventHandler falhou ao processar batch de %d evento(s)", len(events))

    async def run(self) -> None:
        logger.info("Coletor de eventos iniciado (intervalo de %s)", self.interval)
        while True:
            await self.collect_once()
            await asyncio.sleep(self.interval.total_seconds())

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        tasks = list(self._handler_tasks)
        if self._loop_task is not None:
            tasks.append(self._loop_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Coletor de eventos encerrado")
