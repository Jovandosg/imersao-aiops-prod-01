import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from fastapi import FastAPI

from my_agent_app import main
from my_agent_app.agents.correction_executor import CorrectionExecutor
from my_agent_app.agents.handler import AnalysisEventHandler

# Porta sem PostgreSQL: conexao recusada de imediato
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://aiops:aiops123@127.0.0.1:1/aiops_k8s"


@pytest.fixture
def order(monkeypatch):
    calls = []

    class RecordingSource:
        async def list(self):
            calls.append("list")
            return []

    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setattr(main, "KubernetesEventSource", RecordingSource)
    return calls


async def run_lifespan(app):
    async with main.lifespan(app):
        await asyncio.sleep(0.05)


async def test_recuperacao_termina_antes_da_primeira_listagem(monkeypatch, order):
    async def slow_recover(session):
        await asyncio.sleep(0.02)
        order.append("recover")
        return 0

    async def recover_corrections(session):
        order.append("recover_corrections")
        return 0

    monkeypatch.setattr(main.repository, "recover_orphans", slow_recover)
    monkeypatch.setattr(main.repository, "recover_correction_orphans", recover_corrections)
    app = FastAPI()
    await run_lifespan(app)

    assert order[:3] == ["recover", "recover_corrections", "list"]
    assert app.state.sessionmaker is not None


async def test_banco_fora_do_ar_no_startup_nao_impede_o_coletor(order, caplog):
    app = FastAPI()
    with caplog.at_level(logging.ERROR):
        await run_lifespan(app)

    assert "Recuperacao de analises orfas falhou" in caplog.text
    assert order == ["list"]


async def test_coletor_recebe_o_handler_de_analise(monkeypatch, order):
    created = []
    original = main.EventCollector

    def capture(source, handler, interval):
        collector = original(source, handler, interval)
        created.append(collector)
        return collector

    monkeypatch.setattr(main, "EventCollector", capture)
    await run_lifespan(FastAPI())
    [collector] = created
    assert isinstance(collector.handler, AnalysisEventHandler)


async def test_chave_anthropic_vazia_gera_warning(monkeypatch, order, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        await run_lifespan(FastAPI())
    assert "ANTHROPIC_API_KEY vazia" in caplog.text


async def test_recuperacao_de_correcoes_na_mesma_transacao(monkeypatch, order):
    sessions = []

    async def recover(session):
        sessions.append(session)
        return 0

    class FakeSessionmaker:
        def __init__(self, engine, **kwargs):
            pass

        @asynccontextmanager
        async def begin(self):
            yield object()

    monkeypatch.setattr(main, "async_sessionmaker", FakeSessionmaker)
    monkeypatch.setattr(main.repository, "recover_orphans", recover)
    monkeypatch.setattr(main.repository, "recover_correction_orphans", recover)
    await run_lifespan(FastAPI())
    assert len(sessions) == 2 and sessions[0] is sessions[1]


async def test_executor_de_correcao_no_state_e_parado_apos_o_coletor(monkeypatch, order):
    stops = []
    original_collector_stop = main.EventCollector.stop
    original_executor_stop = CorrectionExecutor.stop

    async def collector_stop(self):
        stops.append("collector")
        await original_collector_stop(self)

    async def executor_stop(self):
        stops.append("executor")
        await original_executor_stop(self)

    monkeypatch.setattr(main.EventCollector, "stop", collector_stop)
    monkeypatch.setattr(CorrectionExecutor, "stop", executor_stop)
    app = FastAPI()
    await run_lifespan(app)

    assert isinstance(app.state.correction_executor, CorrectionExecutor)
    assert stops == ["collector", "executor"]


async def test_handler_recebe_o_timeout_de_correcao(monkeypatch, order):
    monkeypatch.setenv("CORRECTION_TIMEOUT_MINUTES", "7")
    created = []
    original = main.EventCollector

    def capture(source, handler, interval):
        created.append(handler)
        return original(source, handler, interval)

    monkeypatch.setattr(main, "EventCollector", capture)
    await run_lifespan(FastAPI())
    [handler] = created
    assert handler.correction_stale_limit == timedelta(minutes=14)
