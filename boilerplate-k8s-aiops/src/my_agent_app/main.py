import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.api.router import router as api_router
from my_agent_app.collector.config import get_interval_minutes
from my_agent_app.collector.handler import EventHandler
from my_agent_app.collector.k8s import KubernetesEventSource
from my_agent_app.collector.loop import EventCollector
from my_agent_app.database import get_database_url
from my_agent_app.web.router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(get_database_url())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    app.state.sessionmaker = sessionmaker

    collector = EventCollector(KubernetesEventSource(), EventHandler(), get_interval_minutes())
    collector.start()

    yield

    await collector.stop()
    await engine.dispose()


app = FastAPI(title="My Agent App", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)
