from datetime import datetime


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def make_event(
    uid: str = "uid-1",
    type: str = "Warning",
    reason: str = "BackOff",
    note: str = "Back-off pulling image",
    namespace: str = "default",
    regarding: dict | None = None,
    series_last_observed: datetime | None = None,
    event_time: datetime | None = None,
    deprecated_last_timestamp: datetime | None = None,
) -> dict:
    """Evento no formato cru da API events.k8s.io/v1."""
    if regarding is None:
        regarding = {"kind": "Pod", "name": "nginx-abc", "namespace": namespace}
    event = {
        "metadata": {"uid": uid, "namespace": namespace},
        "type": type,
        "reason": reason,
        "note": note,
        "regarding": regarding,
        "eventTime": _iso(event_time),
        "deprecatedLastTimestamp": _iso(deprecated_last_timestamp),
    }
    if series_last_observed is not None:
        event["series"] = {"count": 5, "lastObservedTime": _iso(series_last_observed)}
    return event
