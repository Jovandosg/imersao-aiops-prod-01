import logging
import re

from my_agent_app.models.report import ReportStatus

logger = logging.getLogger(__name__)

# Token ancorado no inicio da linha; tolera prefixos Markdown (-, *, #, >) e enfase (**CORRIGIDO:**, __FALHA__:)
VERDICT_LINE = re.compile(r"^\s*(?:[-*#>]+\s*)*(?:\*\*|__)?(CORRIGIDO|FALHA)(?:\*\*|__)?\s*:", re.MULTILINE)


def parse_verdict(text: str) -> str:
    """Regra conservadora: qualquer FALHA vence; CORRIGIDO so sem nenhuma FALHA; sem veredito e FALHA."""
    tokens = set(VERDICT_LINE.findall(text or ""))
    if not tokens:
        logger.warning("Resposta do agente de correcao sem linha de veredito; tratando como FALHA_CORRECAO")
        return ReportStatus.FALHA_CORRECAO
    if "FALHA" in tokens:
        return ReportStatus.FALHA_CORRECAO
    return ReportStatus.CORRIGIDO
