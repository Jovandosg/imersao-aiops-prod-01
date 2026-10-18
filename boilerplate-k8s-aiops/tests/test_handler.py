from my_agent_app.collector.handler import EventHandler

EVENT = {
    "uid": "u-1",
    "type": "Warning",
    "reason": "Failed",
    "message": "Failed to pull image ngin:latest",
    "namespace": "teste-a",
    "involved_object": {"kind": "Pod", "name": "nginx-abc", "namespace": "teste-a"},
    "timestamp": "2026-10-18T12:00:00+00:00",
}


async def test_batch_e_impresso_no_stdout(capsys):
    second = {**EVENT, "uid": "u-2"}
    await EventHandler().handle([EVENT, second])

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3
    assert "2 evento(s)" in lines[0]
    for line, uid in zip(lines[1:], ["u-1", "u-2"]):
        for expected in [
            f"uid={uid}",
            "type=Warning",
            "reason=Failed",
            "namespace=teste-a",
            "involved_object.kind=Pod",
            "involved_object.name=nginx-abc",
            "involved_object.namespace=teste-a",
            "timestamp=2026-10-18T12:00:00+00:00",
            "Failed to pull image ngin:latest",
        ]:
            assert expected in line
