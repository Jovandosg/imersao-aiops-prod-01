import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.agents.analyzer import AgentConfig, RootCauseAnalyzer
from my_agent_app.agents.config import get_retry_cooldown_minutes, get_stale_timeout_minutes
from my_agent_app.agents.correction_executor import CorrectionExecutor
from my_agent_app.agents.corrector import Corrector, CorrectorConfig
from my_agent_app.agents.handler import AnalysisEventHandler
from my_agent_app.api.router import router as api_router
from my_agent_app.collector.config import get_interval_minutes
from my_agent_app.collector.k8s import KubernetesEventSource
from my_agent_app.collector.loop import EventCollector
from my_agent_app.database import get_database_url
from my_agent_app.models import repository
from my_agent_app.web.router import router as web_router

logger = logging.getLogger(__name__)


async def recover_orphans(sessionmaker: async_sessionmaker) -> None:
    """EM_ANALISE -> INCOMPLETO e CORRIGINDO -> FALHA_CORRECAO de uma execucao anterior, numa transacao.

    Banco fora do ar nao impede o startup.
    """
    try:
        async with sessionmaker.begin() as session:
            count = await repository.recover_orphans(session)
            corrections = await repository.recover_correction_orphans(session)
    except Exception as exc:
        logger.error("Recuperacao de analises orfas falhou (o timeout de estagnacao cobre): %s", exc)
        return
    logger.info(
        "Recuperacao de orfaos: %d relatorio(s) EM_ANALISE -> INCOMPLETO, %d CORRIGINDO -> FALHA_CORRECAO",
        count,
        corrections,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(get_database_url())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    app.state.sessionmaker = sessionmaker

    # Antes da primeira coleta: sem filtro temporal, ela veria os orfaos como ativos
    await recover_orphans(sessionmaker)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY vazia: toda analise vai falhar e o relatorio ficara INCOMPLETO")

    corrector_config = CorrectorConfig.from_env()
    correction_executor = CorrectionExecutor(Corrector(sessionmaker, corrector_config))
    app.state.correction_executor = correction_executor

    analyzer = RootCauseAnalyzer(sessionmaker, AgentConfig.from_env())
    handler = AnalysisEventHandler(
        sessionmaker,
        analyzer,
        get_retry_cooldown_minutes(),
        get_stale_timeout_minutes(),
        correction_timeout_minutes=corrector_config.timeout_minutes,
    )
    collector = EventCollector(KubernetesEventSource(), handler, get_interval_minutes())
    collector.start()

    yield

    await collector.stop()
    await correction_executor.stop()
    await engine.dispose()


app = FastAPI(title="My Agent App", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)
