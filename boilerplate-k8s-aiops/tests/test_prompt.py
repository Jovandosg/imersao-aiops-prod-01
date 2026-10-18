import json

from my_agent_app.agents.prompt import build_prompt

EVENTS = [
    {
        "uid": "uid-nginx-1",
        "type": "Warning",
        "reason": "Failed",
        "message": 'Failed to pull image "ngin:latest"',
        "namespace": "teste-a",
        "involved_object": {"kind": "Pod", "name": "nginx-abc", "namespace": "teste-a"},
        "timestamp": "2026-10-18T12:00:00+00:00",
    },
    {
        "uid": "uid-kubenews-1",
        "type": "Warning",
        "reason": "BackOff",
        "message": "Back-off restarting failed container kubenews",
        "namespace": "teste-b",
        "involved_object": {"kind": "Pod", "name": "kubenews-xyz", "namespace": "teste-b"},
        "timestamp": "2026-10-18T12:01:00+00:00",
    },
]


def test_eventos_do_lote_aparecem_no_prompt():
    prompt = build_prompt(EVENTS)
    for event in EVENTS:
        assert event["uid"] in prompt
        assert event["reason"] in prompt
        assert json.dumps(event["message"])[1:-1] in prompt
    assert "{events}" not in prompt


def test_prompt_mantem_o_contrato_de_saida():
    prompt = build_prompt(EVENTS)
    for field in ["**Severidade:**", "**Namespace:**", "**Recursos Afetados:**", "**Eventos:**", "**Conclusao:**"]:
        assert field in prompt
    assert "## Problema 1:" in prompt


def test_comando_sugerido_usa_patch_strategic():
    prompt = build_prompt(EVENTS)
    assert "--type=strategic" in prompt
    assert "--type=merge" not in prompt
