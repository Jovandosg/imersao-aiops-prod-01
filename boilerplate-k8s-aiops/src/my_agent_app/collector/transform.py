import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def recency(event: dict) -> datetime | None:
    """Recencia pela precedencia series.lastObservedTime -> eventTime -> deprecatedLastTimestamp."""
    series = event.get("series") or {}
    return (
        _parse(series.get("lastObservedTime"))
        or _parse(event.get("eventTime"))
        or _parse(event.get("deprecatedLastTimestamp"))
    )


def to_contract(event: dict, timestamp: datetime) -> dict:
    """Evento cru de events.k8s.io/v1 -> dict do contrato de saida."""
    metadata = event.get("metadata") or {}
    regarding = event.get("regarding") or {}
    return {
        "uid": metadata.get("uid", ""),
        "type": event.get("type", ""),
        "reason": event.get("reason") or "",
        "message": event.get("note") or "",
        "namespace": metadata.get("namespace") or "",
        "involved_object": {
            "kind": regarding.get("kind") or "",
            "name": regarding.get("name") or "",
            "namespace": regarding.get("namespace") or "",
        },
        "timestamp": timestamp.isoformat(),
    }


def select_events(
    events: list[dict],
    watermark: datetime | None,
    overlap: timedelta,
) -> list[dict]:
    """Filtra Warnings pela janela e converte para o contrato.

    Sem marca d'agua (primeira coleta) nao ha filtro de recencia. Caso contrario,
    entrega eventos com recencia >= marca - sobreposicao.
    """
    since = watermark - overlap if watermark is not None else None
    selected = []
    for event in events:
        if event.get("type") != "Warning":
            continue
        timestamp = recency(event)
        if timestamp is None:
            uid = (event.get("metadata") or {}).get("uid")
            logger.warning("Evento %s descartado: sem timestamp de recencia", uid)
            continue
        if since is not None and timestamp < since:
            continue
        selected.append(to_contract(event, timestamp))
    return selected
