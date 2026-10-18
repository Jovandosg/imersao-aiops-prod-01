"""Fixtures do marker `db`: PostgreSQL do docker compose, banco `aiops_k8s_test`.

O banco e criado se nao existir e migrado com `alembic upgrade head` uma vez por sessao;
cada teste comeca com a tabela `reports` vazia. Rodar com `uv run pytest -m db`.
"""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.database import get_database_url

TEST_DATABASE = "aiops_k8s_test"
ROOT = Path(__file__).resolve().parent.parent


def database_url_for_tests() -> str:
    return make_url(get_database_url()).set(database=TEST_DATABASE).render_as_string(hide_password=False)


async def _ensure_database(url: str) -> None:
    admin = make_url(url).set(drivername="postgresql", database="postgres")
    conn = await asyncpg.connect(admin.render_as_string(hide_password=False))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DATABASE}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    url = database_url_for_tests()
    try:
        asyncio.run(_ensure_database(url))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"PostgreSQL indisponivel ({exc}); suba com `docker compose up -d`")
    # Sem alembic.ini: o fileConfig do env.py reconfiguraria o logging e quebraria o caplog
    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


@pytest.fixture
async def sessionmaker(migrated_database_url):
    engine = create_async_engine(migrated_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE reports"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
