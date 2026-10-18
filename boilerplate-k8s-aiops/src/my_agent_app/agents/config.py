import logging
import math
import os

logger = logging.getLogger(__name__)

DEFAULT_AGENT_MODEL_NAME = "claude-haiku-4-5"
DEFAULT_AGENT_MAX_ITERATIONS = 25
DEFAULT_MCP_SERVER_URL = "http://localhost:3001/mcp"
DEFAULT_RETRY_COOLDOWN_MINUTES = 30.0
DEFAULT_STALE_TIMEOUT_MINUTES = 30.0
DEFAULT_CORRECTION_MAX_ITERATIONS = 25
DEFAULT_CORRECTION_TIMEOUT_MINUTES = 10.0


def get_agent_model_name() -> str:
    return os.environ.get("AGENT_MODEL_NAME") or DEFAULT_AGENT_MODEL_NAME


def get_mcp_server_url() -> str:
    return os.environ.get("MCP_SERVER_URL") or DEFAULT_MCP_SERVER_URL


def get_correction_model_name() -> str:
    return os.environ.get("CORRECTION_MODEL_NAME") or get_agent_model_name()


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        value = 0

    if value <= 0:
        logger.warning("%s invalido (%r); usando o padrao de %s", name, raw, default)
        return default

    return value


def get_agent_max_iterations() -> int:
    return _positive_int("AGENT_MAX_ITERATIONS", DEFAULT_AGENT_MAX_ITERATIONS)


def get_correction_max_iterations() -> int:
    return _positive_int("CORRECTION_MAX_ITERATIONS", DEFAULT_CORRECTION_MAX_ITERATIONS)


def _positive_minutes(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default

    try:
        value = float(raw)
    except ValueError:
        value = math.nan

    if not math.isfinite(value) or value <= 0:
        logger.warning("%s invalido (%r); usando o padrao de %s minutos", name, raw, default)
        return default

    return value


def get_retry_cooldown_minutes() -> float:
    return _positive_minutes("ANALYSIS_RETRY_COOLDOWN_MINUTES", DEFAULT_RETRY_COOLDOWN_MINUTES)


def get_stale_timeout_minutes() -> float:
    return _positive_minutes("ANALYSIS_STALE_TIMEOUT_MINUTES", DEFAULT_STALE_TIMEOUT_MINUTES)


def get_correction_timeout_minutes() -> float:
    return _positive_minutes("CORRECTION_TIMEOUT_MINUTES", DEFAULT_CORRECTION_TIMEOUT_MINUTES)
