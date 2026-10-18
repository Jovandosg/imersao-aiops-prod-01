import asyncio
import logging
from datetime import UTC, datetime, timedelta

from kubernetes.client.exceptions import ApiException

from my_agent_app.collector.loop import EventCollector
from tests.factories import make_event

T0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)


class FakeSource:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def list(self):
        self.calls += 1
        result = self.results.pop(0) if self.results else []
        if isinstance(result, BaseException):
            raise result
        return result


class RecordingHandler:
    def __init__(self, delay=0.0, error=None):
        self.batches = []
        self.delay = delay
        self.error = error

    async def handle(self, events):
        await asyncio.sleep(self.delay)
        self.batches.append(events)
        if self.error:
            raise self.error


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


async def drain(collector):
    await asyncio.gather(*collector._handler_tasks)


async def test_primeira_coleta_e_imediata():
    source = FakeSource([[make_event(event_time=T0)]])
    handler = RecordingHandler()
    collector = EventCollector(source, handler, interval_minutes=60)
    collector.start()
    await asyncio.sleep(0.05)
    await collector.stop()
    assert source.calls == 1
    assert len(handler.batches) == 1


async def test_marca_dagua_e_capturada_antes_da_listagem():
    clock = FakeClock(T0)

    class AdvancingSource(FakeSource):
        async def list(self):
            clock.now = T0 + timedelta(seconds=30)
            return []

    collector = EventCollector(AdvancingSource([]), RecordingHandler(), interval_minutes=3, clock=clock)
    await collector.collect_once()
    assert collector.watermark == T0


async def test_handler_nao_e_invocado_em_batch_vazio():
    handler = RecordingHandler()
    collector = EventCollector(FakeSource([[]]), handler, interval_minutes=3, clock=FakeClock(T0))
    await collector.collect_once()
    await drain(collector)
    assert handler.batches == []
    assert collector.watermark == T0


async def test_handler_lento_nao_bloqueia_coleta():
    handler = RecordingHandler(delay=1)
    collector = EventCollector(FakeSource([[make_event(event_time=T0)]] * 3), handler, interval_minutes=0.0005)
    collector.start()
    await asyncio.sleep(0.2)
    calls = collector.source.calls
    await collector.stop()
    assert calls >= 3
    assert handler.batches == []  # nenhum handler terminou, e mesmo assim o loop seguiu


async def test_erro_no_handler_e_isolado(caplog):
    handler = RecordingHandler(error=RuntimeError("boom"))
    clock = FakeClock(T0)
    collector = EventCollector(FakeSource([[make_event(event_time=T0)]]), handler, interval_minutes=3, clock=clock)
    with caplog.at_level(logging.ERROR):
        await collector.collect_once()
        await drain(collector)
    assert "EventHandler falhou" in caplog.text
    assert collector.watermark == T0

    clock.now = T0 + timedelta(minutes=3)
    await collector.collect_once()  # loop segue funcionando
    assert collector.watermark == T0 + timedelta(minutes=3)


async def test_falha_de_conectividade_nao_avanca_marca_dagua(caplog):
    clock = FakeClock(T0)
    source = FakeSource([[], ConnectionError("apiserver fora do ar"), []])
    collector = EventCollector(source, RecordingHandler(), interval_minutes=3, clock=clock)
    await collector.collect_once()
    assert collector.watermark == T0

    clock.now = T0 + timedelta(minutes=3)
    with caplog.at_level(logging.ERROR):
        await collector.collect_once()
    assert collector.watermark == T0
    assert "cluster inacessivel" in caplog.text
    assert "Traceback" not in caplog.text

    clock.now = T0 + timedelta(minutes=6)
    await collector.collect_once()
    assert collector.watermark == T0 + timedelta(minutes=6)


async def test_erro_inesperado_na_coleta_e_logado_e_loop_segue(caplog):
    clock = FakeClock(T0)
    collector = EventCollector(FakeSource([ValueError("json invalido"), []]), RecordingHandler(), interval_minutes=3, clock=clock)
    with caplog.at_level(logging.ERROR):
        await collector.collect_once()
    assert "Falha ao coletar eventos" in caplog.text
    assert collector.watermark is None
    await collector.collect_once()
    assert collector.watermark == T0


async def test_rbac_403_loga_permissao_necessaria(caplog):
    clock = FakeClock(T0)
    collector = EventCollector(
        FakeSource([ApiException(status=403, reason="Forbidden")]), RecordingHandler(), interval_minutes=3, clock=clock
    )
    with caplog.at_level(logging.ERROR):
        await collector.collect_once()
    assert "list" in caplog.text and "events.events.k8s.io" in caplog.text
    assert collector.watermark is None


async def test_segunda_coleta_aplica_janela_com_sobreposicao():
    clock = FakeClock(T0)
    old = make_event(uid="old", event_time=T0 - timedelta(minutes=10))
    late = make_event(uid="late", event_time=T0 - timedelta(minutes=1))
    source = FakeSource([[old], [old, late]])
    handler = RecordingHandler()
    collector = EventCollector(source, handler, interval_minutes=3, clock=clock)

    await collector.collect_once()
    clock.now = T0 + timedelta(minutes=3)
    await collector.collect_once()
    await drain(collector)

    assert [[e["uid"] for e in b] for b in handler.batches] == [["old"], ["late"]]


async def test_stop_cancela_tasks_pendentes_do_handler():
    handler = RecordingHandler(delay=10)
    collector = EventCollector(FakeSource([[make_event(event_time=T0)]]), handler, interval_minutes=60)
    collector.start()
    await asyncio.sleep(0.05)
    pending = list(collector._handler_tasks)
    assert pending
    await collector.stop()
    assert all(t.cancelled() for t in pending)
    assert collector._loop_task.cancelled()
