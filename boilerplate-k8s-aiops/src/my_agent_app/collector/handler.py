from datetime import UTC, datetime


class EventHandler:
    """Placeholder: imprime o batch no stdout. O PRD 002 substitui por outra implementacao."""

    async def handle(self, events: list[dict]) -> None:
        collected_at = datetime.now(UTC).isoformat()
        lines = [f"=== {len(events)} evento(s) Warning coletado(s) em {collected_at} ==="]
        for event in events:
            obj = event["involved_object"]
            lines.append(
                f"uid={event['uid']} type={event['type']} reason={event['reason']} "
                f"namespace={event['namespace']} "
                f"involved_object.kind={obj['kind']} involved_object.name={obj['name']} "
                f"involved_object.namespace={obj['namespace']} "
                f"timestamp={event['timestamp']} message={event['message']!r}"
            )
        print("\n".join(lines), flush=True)
