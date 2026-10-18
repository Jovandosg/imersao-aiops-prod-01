"""Integracao contra o cluster kind local (`kind-aiops`).

Pre-requisitos: roteiro de setup do README (namespaces teste-a/teste-b com os
manifestos de manifestos-k8s/ aplicados). Rodar com `uv run pytest -m kind`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from kubernetes import client, config

from my_agent_app.collector.k8s import KubernetesEventSource
from my_agent_app.collector.transform import recency, select_events

pytestmark = pytest.mark.kind

KIND_CONTEXT = "kind-aiops"
CONTRACT_KEYS = {"uid", "type", "reason", "message", "namespace", "involved_object", "timestamp"}


@pytest.fixture(scope="module", autouse=True)
def require_kind_context():
    try:
        _, active = config.list_kube_config_contexts()
    except Exception as exc:
        pytest.skip(f"kubeconfig indisponivel: {exc}")
    if active["name"] != KIND_CONTEXT:
        pytest.skip(f"contexto ativo e {active['name']!r}; estes testes so rodam em {KIND_CONTEXT!r}")
    config.load_kube_config()


@pytest.fixture
async def raw_events():
    return await KubernetesEventSource().list()


async def test_field_selector_warning_e_aceito_e_retorna_so_warning(raw_events):
    assert raw_events
    assert {e["type"] for e in raw_events} == {"Warning"}


async def test_coleta_cobre_os_namespaces_de_teste(raw_events):
    namespaces = {e["metadata"]["namespace"] for e in raw_events}
    assert {"teste-a", "teste-b"} <= namespaces


async def test_eventos_do_nginx_seguem_o_contrato(raw_events):
    events = [e for e in select_events(raw_events, None, timedelta(minutes=3)) if e["namespace"] == "teste-a"]
    nginx = [e for e in events if e["involved_object"]["name"].startswith("nginx-")]
    assert nginx

    for event in nginx:
        assert set(event) == CONTRACT_KEYS
        assert set(event["involved_object"]) == {"kind", "name", "namespace"}
        assert all(isinstance(event[k], str) for k in CONTRACT_KEYS - {"involved_object"})
        assert event["involved_object"]["kind"] == "Pod"
        assert event["involved_object"]["namespace"] == "teste-a"
        assert datetime.fromisoformat(event["timestamp"]).tzinfo is not None


async def test_backoff_recorrente_do_kube_news_usa_deprecated_last_timestamp(raw_events):
    # O kubelet emite eventos legados: a recorrencia vem em deprecatedCount/deprecatedLastTimestamp, sem series.
    backoffs = [
        e for e in raw_events
        if e["metadata"]["namespace"] == "teste-b" and e["reason"] == "BackOff"
    ]
    assert backoffs
    recurring = max(backoffs, key=lambda e: e.get("deprecatedCount") or 0)
    assert recency(recurring) == datetime.fromisoformat(recurring["deprecatedLastTimestamp"])


async def test_evento_com_series_usa_last_observed_time():
    pod = client.CoreV1Api().list_namespaced_pod("teste-b", label_selector="app=kubenews").items[0]
    now = datetime.now(UTC)
    first = now - timedelta(minutes=30)
    name = f"aiops-series-{uuid.uuid4().hex[:8]}"
    body = {
        "apiVersion": "events.k8s.io/v1",
        "kind": "Event",
        "metadata": {"name": name, "namespace": "teste-b"},
        "type": "Warning",
        "reason": "BackOff",
        "note": "evento sintetico com series (teste de integracao)",
        "action": "Restarting",
        "reportingController": "aiops.test/collector",
        "reportingInstance": "pytest",
        "eventTime": first.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "series": {"count": 4, "lastObservedTime": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")},
        "regarding": {"apiVersion": "v1", "kind": "Pod", "name": pod.metadata.name, "namespace": "teste-b"},
    }
    api = client.EventsV1Api()
    api.create_namespaced_event("teste-b", body, _preload_content=False)
    try:
        raw = await KubernetesEventSource().list()
        [created] = [e for e in raw if e["metadata"]["name"] == name]
        # Janela que exclui o eventTime: so a precedencia de series mantem o evento.
        [event] = select_events([created], watermark=now, overlap=timedelta(minutes=3))
        assert datetime.fromisoformat(event["timestamp"]) == datetime.fromisoformat(
            created["series"]["lastObservedTime"]
        )
    finally:
        api.delete_namespaced_event(name, "teste-b")
