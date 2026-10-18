import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from my_agent_app.models import repository
from my_agent_app.models.report import Report, ReportStatus
from my_agent_app.web.rendering import render_markdown

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

DB_ERRORS = (SQLAlchemyError, OSError)
DB_UNAVAILABLE_MESSAGE = "Banco de dados indisponível, tente novamente em instantes"

STATUS_BADGES = {
    ReportStatus.EM_ANALISE: "badge-processing",
    ReportStatus.COMPLETO: "badge-complete",
    ReportStatus.INCOMPLETO: "badge-incomplete",
    ReportStatus.CORRIGINDO: "badge-executing",
    ReportStatus.CORRIGIDO: "badge-executed",
    ReportStatus.FALHA_CORRECAO: "badge-execution-failed",
}

ERROR_MESSAGES = {
    "em_andamento": "Correção já em andamento",
    "status_invalido": "A correção não pode ser iniciada no status atual do relatório",
}


def status_badge(status: str) -> str:
    return STATUS_BADGES.get(status, "")


def report_title(report: Report) -> str:
    return report.title or f"Análise em lote {str(report.id)[:8]}"


templates.env.globals.update(status_badge=status_badge, report_title=report_title)


def _error(request: Request, status_code: int, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "error.html", {"status_code": status_code, "message": message}, status_code=status_code
    )


def _db_unavailable(request: Request, exc: Exception) -> HTMLResponse:
    logger.error("Banco indisponivel em %s %s: %s", request.method, request.url.path, exc)
    return _error(request, 503, DB_UNAVAILABLE_MESSAGE)


def _not_found(request: Request) -> HTMLResponse:
    return _error(request, 404, "Relatório não encontrado")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request):
    try:
        async with request.app.state.sessionmaker() as session:
            reports = await repository.list_reports(session)
    except DB_ERRORS as exc:
        return _db_unavailable(request, exc)
    return templates.TemplateResponse(request, "reports.html", {"reports": reports})


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(request: Request, report_id: uuid.UUID, erro: str | None = None):
    try:
        async with request.app.state.sessionmaker() as session:
            report = await repository.get_report(session, report_id)
    except DB_ERRORS as exc:
        return _db_unavailable(request, exc)
    if report is None:
        return _not_found(request)

    context = {
        "report": report,
        "report_html": render_markdown(report.markdown) if report.markdown else None,
        "correction_html": render_markdown(report.correction_result) if report.correction_result else None,
        "correctable": report.status in repository.CORRECTABLE_STATUSES,
        "error_message": ERROR_MESSAGES.get(erro),
    }
    return templates.TemplateResponse(request, "report_detail.html", context)


@router.post("/reports/{report_id}/fix")
async def fix_report(request: Request, report_id: uuid.UUID):
    detail_url = f"/reports/{report_id}"
    try:
        async with request.app.state.sessionmaker.begin() as session:
            started = await repository.start_correction(session, report_id)
            status = None if started else await repository.get_status(session, report_id)
    except DB_ERRORS as exc:
        return _db_unavailable(request, exc)

    if started:
        # So depois do commit: a task nunca le um relatorio ainda nao comitado
        request.app.state.correction_executor.dispatch(report_id)
        return RedirectResponse(detail_url, status_code=303)
    if status is None:
        return _not_found(request)
    reason = "em_andamento" if status == ReportStatus.CORRIGINDO else "status_invalido"
    return RedirectResponse(f"{detail_url}?erro={reason}", status_code=303)
