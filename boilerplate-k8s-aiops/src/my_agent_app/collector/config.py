import logging
import math
import os

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 3.0


def get_interval_minutes() -> float:
    raw = os.environ.get("EVENT_COLLECTION_INTERVAL_MINUTES")
    if raw is None:
        return DEFAULT_INTERVAL_MINUTES

    try:
        value = float(raw)
    except ValueError:
        value = math.nan

    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "EVENT_COLLECTION_INTERVAL_MINUTES invalido (%r); usando o padrao de %s minutos",
            raw,
            DEFAULT_INTERVAL_MINUTES,
        )
        return DEFAULT_INTERVAL_MINUTES

    return value
