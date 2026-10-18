import logging
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass

from my_agent_app.models.report import ReportStatus

logger = logging.getLogger(__name__)

SEVERITIES = {"CRITICO", "ALTO", "MEDIO", "BAIXO"}

_HEADER = re.compile(r"^##\s+Problema\s+\d+\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_TRAILING_RULE = re.compile(r"(\s*^-{3,}\s*)+\Z", re.MULTILINE)


@dataclass
class Problem:
    title: str
    severity: str | None
    namespace: str | None
    event_uids: list[str]
    status: str
    markdown: str


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def _clean(value: str) -> str:
    return value.strip().strip("`*_[]").strip()


def _field(section: str, name: str) -> str | None:
    """Valor de `- **Nome:** valor`, tolerando caixa e acentos no nome do campo."""
    for match in re.finditer(r"^\s*[-*]\s*\*\*(.+?):\*\*\s*(.*?)\s*$", section, re.MULTILINE):
        if _ascii(match.group(1)).strip().lower() == name:
            return match.group(2)
    return None


def _severity(raw: str | None, title: str) -> str | None:
    value = _ascii(_clean(raw or "")).upper()
    if value in SEVERITIES:
        return value
    logger.warning("Problema %r: severidade ausente ou desconhecida (%r)", title, raw)
    return None


def _status(raw: str | None, title: str) -> str:
    value = _ascii(_clean(raw or "")).lower()
    if value == "conclusiva":
        return ReportStatus.COMPLETO
    if value == "inconclusiva":
        return ReportStatus.INCOMPLETO
    logger.warning("Problema %r: conclusao ausente ou desconhecida (%r); assumindo COMPLETO", title, raw)
    return ReportStatus.COMPLETO


def parse_report(text: str, batch_uids: Collection[str]) -> list[Problem]:
    """Divide a resposta do agente em um Problem por secao `## Problema N: <causa>`."""
    headers = list(_HEADER.finditer(text or ""))
    batch = set(batch_uids)
    assigned: set[str] = set()
    problems = []

    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        title = _clean(header.group(1))
        body = _TRAILING_RULE.sub("", text[header.end():end]).rstrip()

        uids = []
        for uid in (_clean(u) for u in re.split(r"[,\s]+", _field(body, "eventos") or "")):
            if not uid:
                continue
            if uid not in batch:
                logger.warning("Problema %r cita o uid %s, que nao pertence ao lote; descartado", title, uid)
            elif uid in assigned:
                logger.warning("Uid %s citado em mais de um problema; mantido so no primeiro", uid)
            else:
                assigned.add(uid)
                uids.append(uid)
        if not uids:
            logger.warning("Problema %r ficou sem nenhum uid valido do lote", title)

        namespace = _clean(_field(body, "namespace") or "") or None
        problems.append(
            Problem(
                title=title,
                severity=_severity(_field(body, "severidade"), title),
                namespace=namespace,
                event_uids=uids,
                status=_status(_field(body, "conclusao"), title),
                markdown=f"# {title}{body}",
            )
        )

    if problems:
        missing = [u for u in batch_uids if u not in assigned]
        if missing:
            logger.warning("Uids do lote nao citados em nenhum problema: %s", ", ".join(missing))
    return problems
