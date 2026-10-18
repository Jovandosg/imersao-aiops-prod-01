import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from my_agent_app.models.report import ReportStatus
from my_agent_app.web import router as web_module

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
FORM = re.compile(r'<form method="post" action="/reports/[0-9a-f-]+/fix"')
BADGES = {
    ReportStatus.EM_ANALISE: "badge-processing",
    ReportStatus.COMPLETO: "badge-complete",
    ReportStatus.INCOMPLETO: "badge-incomplete",
    ReportStatus.CORRIGINDO: "badge-executing",
    ReportStatus.CORRIGIDO: "badge-executed",
    ReportStatus.FALHA_CORRECAO: "badge-execution-failed",
}


@dataclass
class FakeReport:
    status: str = ReportStatus.COMPLETO
    title: str | None = "Imagem inexistente"
    severity: str | None = "CRITICO"
    namespace: str | None = "teste-a"
    markdown: str | None = "# Imagem inexistente\n\nNOMINATED NODE <none>\n"
    event_uids: list[str] = field(default_factory=lambda: ["uid-1", "uid-2"])
    created_at: datetime = NOW
    correction_result: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class FakeRepository:
    """Mesma interface de `models.repository` usada pelo router, em memoria."""

    CORRECTABLE_STATUSES = (ReportStatus.COMPLETO, ReportStatus.FALHA_CORRECAO)

    def __init__(self, reports=(), error: Exception | None = None):
        self.reports = {r.id: r for r in reports}
        self.error = error

    def _check(self):
        if self.error:
            raise self.error

    async def list_reports(self, session):
        self._check()
        return sorted(self.reports.values(), key=lambda r: r.created_at, reverse=True)

    async def get_report(self, session, report_id):
        self._check()
        return self.reports.get(report_id)

    async def get_status(self, session, report_id):
        report = self.reports.get(report_id)
        return report.status if report else None

    async def start_correction(self, session, report_id):
        self._check()
        report = self.reports.get(report_id)
        if report is None or report.status not in self.CORRECTABLE_STATUSES:
            return False
        report.status = ReportStatus.CORRIGINDO
        report.correction_result = None
        return True


class FakeSessionmaker:
    def __init__(self):
        self.committed = 0

    @asynccontextmanager
    async def __call__(self):
        yield object()

    @asynccontextmanager
    async def begin(self):
        yield object()
        self.committed += 1


class FakeExecutor:
    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker
        self.dispatched = []
        self.commits_at_dispatch = []

    def dispatch(self, report_id):
        self.dispatched.append(report_id)
        self.commits_at_dispatch.append(self.sessionmaker.committed)


@pytest.fixture
def make_client(monkeypatch):
    def make(*reports, error=None):
        repo = FakeRepository(reports, error)
        monkeypatch.setattr(web_module, "repository", repo)
        app = FastAPI()
        app.include_router(web_module.router)
        app.state.sessionmaker = FakeSessionmaker()
        app.state.correction_executor = FakeExecutor(app.state.sessionmaker)
        client = TestClient(app, follow_redirects=False)
        client.executor = app.state.correction_executor
        client.repo = repo
        return client

    return make


# Listagem


def test_listagem_mais_recente_primeiro(make_client):
    old = FakeReport(title="Antigo", created_at=NOW - timedelta(hours=1))
    new = FakeReport(title="Novo", created_at=NOW)
    html = make_client(old, new).get("/reports").text
    assert html.index("Novo") < html.index("Antigo")


def test_listagem_sem_titulo_nem_severidade(make_client):
    report = FakeReport(status=ReportStatus.EM_ANALISE, title=None, severity=None, markdown=None)
    html = make_client(report).get("/reports").text
    assert f"Análise em lote {str(report.id)[:8]}" in html
    assert "—" in html


def test_item_leva_ao_detalhe(make_client):
    a, b = FakeReport(), FakeReport()
    html = make_client(a, b).get("/reports").text
    assert f'href="/reports/{a.id}"' in html
    assert f'href="/reports/{b.id}"' in html


def test_listagem_vazia(make_client):
    response = make_client().get("/reports")
    assert response.status_code == 200
    assert "Nenhum relatório encontrado" in response.text


def test_badges_dos_seis_status(make_client):
    reports = [FakeReport(status=s, title=f"titulo-{s}") for s in BADGES]
    html = make_client(*reports).get("/reports").text
    for status, badge in BADGES.items():
        assert re.search(rf'class="badge {badge}">{status}<', html), status


@pytest.mark.parametrize("error", [
    OperationalError("SELECT 1", {}, ConnectionRefusedError("recusada")),
    ConnectionRefusedError("recusada"),
])
def test_listagem_banco_indisponivel(make_client, error):
    response = make_client(error=error).get("/reports")
    assert response.status_code == 503
    assert "Banco de dados indisponível, tente novamente em instantes" in response.text


def test_cabecalho_tem_link_relatorios(make_client):
    html = make_client().get("/reports").text
    assert '<a href="/reports">Relatórios</a>' in html
    assert "Tasks" not in html


# Detalhe


def test_detalhe_completo(make_client):
    report = FakeReport()
    response = make_client(report).get(f"/reports/{report.id}")
    assert response.status_code == 200
    html = response.text
    assert "badge-complete" in html
    assert "CRITICO" in html and "teste-a" in html
    assert "uid-1" in html and "uid-2" in html
    assert "<h1>Imagem inexistente</h1>" in html
    assert "&lt;none&gt;" in html and "<none>" not in html


def test_detalhe_em_analise_sem_markdown(make_client):
    report = FakeReport(status=ReportStatus.EM_ANALISE, markdown=None, title=None)
    html = make_client(report).get(f"/reports/{report.id}").text
    assert "Análise em andamento — atualize a página em instantes" in html


def test_detalhe_incompleto_sem_markdown(make_client):
    report = FakeReport(status=ReportStatus.INCOMPLETO, markdown=None)
    html = make_client(report).get(f"/reports/{report.id}").text
    assert "Análise não concluída — será reavaliada na próxima ocorrência dos eventos" in html


def test_detalhe_markdown_malformado(make_client):
    report = FakeReport(markdown="```\nsem fechamento\n**negrito")
    assert make_client(report).get(f"/reports/{report.id}").status_code == 200


def test_detalhe_inexistente_404(make_client):
    response = make_client().get(f"/reports/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "Voltar para relatórios" in response.text


def test_detalhe_id_invalido_422(make_client):
    assert make_client().get("/reports/abc").status_code == 422


@pytest.mark.parametrize("error", [
    OperationalError("SELECT 1", {}, ConnectionRefusedError("recusada")),
    ConnectionRefusedError("recusada"),
])
def test_detalhe_banco_indisponivel(make_client, error):
    response = make_client(error=error).get(f"/reports/{uuid.uuid4()}")
    assert response.status_code == 503
    assert "Banco de dados indisponível" in response.text


@pytest.mark.parametrize("status", list(BADGES))
def test_botao_de_correcao_por_status(make_client, status):
    report = FakeReport(status=status)
    html = make_client(report).get(f"/reports/{report.id}").text
    expected = status in (ReportStatus.COMPLETO, ReportStatus.FALHA_CORRECAO)
    assert bool(FORM.search(html)) is expected
    assert ("Executar correção" in html) is expected


@pytest.mark.parametrize("erro, message", [
    ("em_andamento", "Correção já em andamento"),
    ("status_invalido", "A correção não pode ser iniciada no status atual do relatório"),
])
def test_mensagem_por_parametro(make_client, erro, message):
    report = FakeReport(status=ReportStatus.CORRIGINDO)
    assert message in make_client(report).get(f"/reports/{report.id}?erro={erro}").text


def test_parametro_desconhecido_nao_mostra_mensagem(make_client):
    report = FakeReport()
    html = make_client(report).get(f"/reports/{report.id}?erro=xyz").text
    assert 'class="alert"' not in html


def test_resultado_da_correcao_presente(make_client):
    report = FakeReport(status=ReportStatus.CORRIGIDO, correction_result="CORRIGIDO: ok\n\n## Acoes Executadas\n<none>")
    html = make_client(report).get(f"/reports/{report.id}").text
    assert "Resultado da Correção" in html
    assert "<h2>Acoes Executadas</h2>" in html
    assert "&lt;none&gt;" in html


def test_resultado_da_correcao_ausente(make_client):
    report = FakeReport(correction_result=None)
    assert "Resultado da Correção" not in make_client(report).get(f"/reports/{report.id}").text


# POST /fix


@pytest.mark.parametrize("status", [ReportStatus.COMPLETO, ReportStatus.FALHA_CORRECAO])
def test_fix_despacha_apos_commit_e_redireciona(make_client, status):
    report = FakeReport(status=status, correction_result="anterior")
    client = make_client(report)
    response = client.post(f"/reports/{report.id}/fix")
    assert response.status_code == 303
    assert response.headers["location"] == f"/reports/{report.id}"
    assert client.executor.dispatched == [report.id]
    assert client.executor.commits_at_dispatch == [1]
    assert report.status == ReportStatus.CORRIGINDO
    assert report.correction_result is None


def test_fix_em_andamento(make_client):
    report = FakeReport(status=ReportStatus.CORRIGINDO)
    client = make_client(report)
    response = client.post(f"/reports/{report.id}/fix")
    assert response.status_code == 303
    assert response.headers["location"] == f"/reports/{report.id}?erro=em_andamento"
    assert client.executor.dispatched == []


@pytest.mark.parametrize("status", [ReportStatus.EM_ANALISE, ReportStatus.INCOMPLETO, ReportStatus.CORRIGIDO])
def test_fix_status_invalido(make_client, status):
    report = FakeReport(status=status)
    client = make_client(report)
    response = client.post(f"/reports/{report.id}/fix")
    assert response.status_code == 303
    assert response.headers["location"] == f"/reports/{report.id}?erro=status_invalido"
    assert report.status == status
    assert client.executor.dispatched == []


def test_fix_inexistente_404(make_client):
    client = make_client()
    assert client.post(f"/reports/{uuid.uuid4()}/fix").status_code == 404
    assert client.executor.dispatched == []


def test_fix_banco_indisponivel_503(make_client):
    client = make_client(error=OperationalError("UPDATE", {}, ConnectionRefusedError("recusada")))
    response = client.post(f"/reports/{uuid.uuid4()}/fix")
    assert response.status_code == 503
    assert client.executor.dispatched == []
