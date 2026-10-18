import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from my_agent_app.models import repository
from my_agent_app.models.report import Report, ReportStatus

pytestmark = pytest.mark.db

STALE = timedelta(minutes=30)


@dataclass
class P:
    title: str
    event_uids: list[str]
    status: str = ReportStatus.COMPLETO
    severity: str | None = "CRITICO"
    namespace: str | None = "teste-a"
    markdown: str = "# x"


async def add(sessionmaker, **values) -> Report:
    async with sessionmaker.begin() as session:
        report = Report(**{"status": ReportStatus.COMPLETO, "event_uids": ["u1"], **values})
        session.add(report)
    return report


async def get(sessionmaker, report_id) -> Report:
    async with sessionmaker() as session:
        return await session.get(Report, report_id)


async def all_reports(sessionmaker) -> list[Report]:
    async with sessionmaker() as session:
        return list((await session.execute(select(Report).order_by(Report.created_at))).scalars())


async def db_now(sessionmaker) -> datetime:
    async with sessionmaker() as session:
        return await session.scalar(select(func.now()))


async def test_migration_cria_colunas_e_indice_gin(sessionmaker):
    async with sessionmaker() as session:
        columns = set(
            (await session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'reports'")
            )).scalars()
        )
        indexdef = await session.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_reports_event_uids'")
        )
    assert columns == {
        "id", "markdown", "status", "event_uids", "severity", "namespace", "title",
        "created_at", "updated_at", "corrected_at", "correction_result", "correction_started_at",
    }
    assert "USING gin (event_uids)" in indexdef


async def test_status_invalido_e_rejeitado(sessionmaker):
    with pytest.raises(IntegrityError):
        await add(sessionmaker, status="QUALQUER")


async def test_atualizacao_avanca_updated_at_e_preserva_created_at(sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.EM_ANALISE)
    before = await get(sessionmaker, report.id)
    await asyncio.sleep(0.01)
    async with sessionmaker.begin() as session:
        assert await repository.mark_incomplete(session, report.id)
    after = await get(sessionmaker, report.id)
    assert after.status == ReportStatus.INCOMPLETO
    assert after.updated_at > before.updated_at
    assert after.created_at == before.created_at


async def test_onupdate_do_orm_avanca_updated_at(sessionmaker):
    report = await add(sessionmaker)
    before = await get(sessionmaker, report.id)
    await asyncio.sleep(0.01)
    async with sessionmaker.begin() as session:
        (await session.get(Report, report.id)).title = "novo"
    assert (await get(sessionmaker, report.id)).updated_at > before.updated_at


async def test_find_overlapping_traz_todos_os_status_que_contem_algum_uid(sessionmaker):
    a = await add(sessionmaker, event_uids=["u1", "u2"], status=ReportStatus.CORRIGIDO)
    b = await add(sessionmaker, event_uids=["u3"], status=ReportStatus.INCOMPLETO)
    await add(sessionmaker, event_uids=["outro"])
    async with sessionmaker() as session:
        found = await repository.find_overlapping(session, ["u2", "u3", "u9"])
    assert {r.id for r in found} == {a.id, b.id}


async def test_mark_stale_so_afeta_em_analise_antigo(sessionmaker):
    now = await db_now(sessionmaker)
    old = await add(sessionmaker, status=ReportStatus.EM_ANALISE, created_at=now - timedelta(minutes=31))
    recent = await add(sessionmaker, status=ReportStatus.EM_ANALISE, created_at=now - timedelta(minutes=5))
    completo = await add(sessionmaker, status=ReportStatus.COMPLETO, created_at=now - timedelta(hours=2))
    async with sessionmaker.begin() as session:
        assert await repository.mark_stale(session, now, STALE) == 1
    assert (await get(sessionmaker, old.id)).status == ReportStatus.INCOMPLETO
    assert (await get(sessionmaker, recent.id)).status == ReportStatus.EM_ANALISE
    assert (await get(sessionmaker, completo.id)).status == ReportStatus.COMPLETO


async def test_create_in_analysis(sessionmaker):
    async with sessionmaker.begin() as session:
        report_id = await repository.create_in_analysis(session, ["u1", "u2"])
    report = await get(sessionmaker, report_id)
    assert report.status == ReportStatus.EM_ANALISE
    assert report.event_uids == ["u1", "u2"]
    assert report.markdown is None


async def test_mark_incomplete_nao_sobrescreve_relatorio_fora_de_em_analise(sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.COMPLETO, markdown="# ok")
    async with sessionmaker.begin() as session:
        assert not await repository.mark_incomplete(session, report.id)
    after = await get(sessionmaker, report.id)
    assert after.status == ReportStatus.COMPLETO
    assert after.markdown == "# ok"


async def test_recover_orphans(sessionmaker):
    orphan = await add(sessionmaker, status=ReportStatus.EM_ANALISE)
    other = await add(sessionmaker, status=ReportStatus.CORRIGINDO)
    async with sessionmaker.begin() as session:
        assert await repository.recover_orphans(session) == 1
    assert (await get(sessionmaker, orphan.id)).status == ReportStatus.INCOMPLETO
    assert (await get(sessionmaker, other.id)).status == ReportStatus.CORRIGINDO


async def test_swap_batch_preserva_id_e_insere_demais(sessionmaker):
    batch = await add(sessionmaker, status=ReportStatus.EM_ANALISE, event_uids=["u1", "u2", "u3"])
    problems = [
        P("Imagem inexistente", ["u1"]),
        P("Senha do banco", ["u2", "u3"], status=ReportStatus.INCOMPLETO, severity="ALTO", namespace="teste-b"),
    ]
    async with sessionmaker.begin() as session:
        assert await repository.swap_batch(session, batch.id, problems)

    reports = {r.title: r for r in await all_reports(sessionmaker)}
    assert len(reports) == 2
    first = reports["Imagem inexistente"]
    assert first.id == batch.id
    assert (first.status, first.severity, first.namespace, first.event_uids) == (
        ReportStatus.COMPLETO, "CRITICO", "teste-a", ["u1"]
    )
    second = reports["Senha do banco"]
    assert second.id != batch.id
    assert (second.status, second.severity, second.namespace, second.event_uids) == (
        ReportStatus.INCOMPLETO, "ALTO", "teste-b", ["u2", "u3"]
    )


async def test_swap_batch_aborta_quando_lote_saiu_de_em_analise(sessionmaker):
    batch = await add(sessionmaker, status=ReportStatus.INCOMPLETO, event_uids=["u1", "u2"])
    async with sessionmaker.begin() as session:
        assert not await repository.swap_batch(session, batch.id, [P("a", ["u1"]), P("b", ["u2"])])
    [only] = await all_reports(sessionmaker)
    assert only.id == batch.id
    assert only.status == ReportStatus.INCOMPLETO
    assert only.title is None


async def test_swap_batch_id_inexistente(sessionmaker):
    async with sessionmaker.begin() as session:
        assert not await repository.swap_batch(session, uuid.uuid4(), [P("a", ["u1"])])
    assert await all_reports(sessionmaker) == []


async def test_migration_correction_started_at_nula_e_com_fuso(sessionmaker):
    report = await add(sessionmaker)
    async with sessionmaker() as session:
        data_type, nullable = (await session.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'reports' AND column_name = 'correction_started_at'"
            )
        )).one()
    assert (data_type, nullable) == ("timestamp with time zone", "YES")
    assert (await get(sessionmaker, report.id)).correction_started_at is None


async def test_list_reports_mais_recente_primeiro(sessionmaker):
    now = await db_now(sessionmaker)
    old = await add(sessionmaker, created_at=now - timedelta(hours=2))
    new = await add(sessionmaker, created_at=now)
    middle = await add(sessionmaker, created_at=now - timedelta(hours=1))
    async with sessionmaker() as session:
        reports = await repository.list_reports(session)
    assert [r.id for r in reports] == [new.id, middle.id, old.id]


async def test_get_report(sessionmaker):
    report = await add(sessionmaker, title="x")
    async with sessionmaker() as session:
        assert (await repository.get_report(session, report.id)).title == "x"
        assert await repository.get_report(session, uuid.uuid4()) is None
        assert await repository.get_status(session, report.id) == ReportStatus.COMPLETO
        assert await repository.get_status(session, uuid.uuid4()) is None


@pytest.mark.parametrize("status", [ReportStatus.COMPLETO, ReportStatus.FALHA_CORRECAO])
async def test_start_correction_transiciona_e_limpa_resultado(sessionmaker, status):
    report = await add(sessionmaker, status=status, correction_result="tentativa anterior")
    async with sessionmaker.begin() as session:
        assert await repository.start_correction(session, report.id)
    after = await get(sessionmaker, report.id)
    assert after.status == ReportStatus.CORRIGINDO
    assert after.correction_result is None
    assert after.correction_started_at is not None


@pytest.mark.parametrize(
    "status",
    [ReportStatus.EM_ANALISE, ReportStatus.INCOMPLETO, ReportStatus.CORRIGINDO, ReportStatus.CORRIGIDO],
)
async def test_start_correction_rejeita_demais_status(sessionmaker, status):
    report = await add(sessionmaker, status=status, correction_result="r")
    async with sessionmaker.begin() as session:
        assert not await repository.start_correction(session, report.id)
    after = await get(sessionmaker, report.id)
    assert (after.status, after.correction_result, after.correction_started_at) == (status, "r", None)


async def test_start_correction_inexistente(sessionmaker):
    async with sessionmaker.begin() as session:
        assert not await repository.start_correction(session, uuid.uuid4())


async def test_start_correction_concorrente_so_um_vence(sessionmaker):
    report = await add(sessionmaker)

    async def attempt():
        async with sessionmaker.begin() as session:
            return await repository.start_correction(session, report.id)

    results = await asyncio.gather(attempt(), attempt(), attempt())
    assert sorted(results) == [False, False, True]


async def test_finish_correction_corrigido_preenche_corrected_at(sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.CORRIGINDO)
    async with sessionmaker.begin() as session:
        assert await repository.finish_correction(session, report.id, ReportStatus.CORRIGIDO, "CORRIGIDO: ok")
    after = await get(sessionmaker, report.id)
    assert (after.status, after.correction_result) == (ReportStatus.CORRIGIDO, "CORRIGIDO: ok")
    assert after.corrected_at is not None


async def test_finish_correction_falha_preserva_corrected_at(sessionmaker):
    previous = (await db_now(sessionmaker)) - timedelta(days=1)
    report = await add(sessionmaker, status=ReportStatus.CORRIGINDO, corrected_at=previous)
    async with sessionmaker.begin() as session:
        assert await repository.finish_correction(session, report.id, ReportStatus.FALHA_CORRECAO, "FALHA: x")
    after = await get(sessionmaker, report.id)
    assert (after.status, after.correction_result) == (ReportStatus.FALHA_CORRECAO, "FALHA: x")
    assert after.corrected_at == previous


async def test_finish_correction_nao_sobrescreve_estado_posterior(sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.FALHA_CORRECAO, correction_result="interrompida")
    async with sessionmaker.begin() as session:
        assert not await repository.finish_correction(session, report.id, ReportStatus.CORRIGIDO, "atrasado")
    after = await get(sessionmaker, report.id)
    assert (after.status, after.correction_result, after.corrected_at) == (
        ReportStatus.FALHA_CORRECAO, "interrompida", None
    )


async def test_recover_correction_orphans(sessionmaker):
    orphan = await add(sessionmaker, status=ReportStatus.CORRIGINDO)
    other = await add(sessionmaker, status=ReportStatus.EM_ANALISE)
    async with sessionmaker.begin() as session:
        assert await repository.recover_correction_orphans(session) == 1
    after = await get(sessionmaker, orphan.id)
    assert after.status == ReportStatus.FALHA_CORRECAO
    assert after.correction_result == repository.CORRECTION_INTERRUPTED_MESSAGE
    assert (await get(sessionmaker, other.id)).status == ReportStatus.EM_ANALISE


async def test_mark_correction_stale_usa_correction_started_at(sessionmaker):
    now = await db_now(sessionmaker)
    limit = timedelta(minutes=20)
    stale = await add(sessionmaker, status=ReportStatus.CORRIGINDO, correction_started_at=now - timedelta(minutes=21))
    # Relatorio antigo, mas a correcao comecou agora: created_at nao conta
    alive = await add(
        sessionmaker,
        status=ReportStatus.CORRIGINDO,
        created_at=now - timedelta(days=2),
        correction_started_at=now - timedelta(minutes=19),
    )
    other = await add(sessionmaker, status=ReportStatus.COMPLETO, correction_started_at=now - timedelta(hours=1))
    async with sessionmaker.begin() as session:
        assert await repository.mark_correction_stale(session, now, limit) == 1
    after = await get(sessionmaker, stale.id)
    assert after.status == ReportStatus.FALHA_CORRECAO
    assert after.correction_result == repository.CORRECTION_INTERRUPTED_MESSAGE
    assert (await get(sessionmaker, alive.id)).status == ReportStatus.CORRIGINDO
    assert (await get(sessionmaker, other.id)).status == ReportStatus.COMPLETO
