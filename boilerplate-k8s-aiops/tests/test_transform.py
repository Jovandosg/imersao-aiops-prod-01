import logging
from datetime import UTC, datetime, timedelta

from my_agent_app.collector.transform import recency, select_events, to_contract
from tests.factories import make_event

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=3)


# Precedencia

def test_series_tem_precedencia_sobre_event_time_antigo():
    event = make_event(series_last_observed=NOW, event_time=NOW - timedelta(hours=1))
    assert recency(event) == NOW


def test_sem_series_usa_event_time():
    event = make_event(event_time=NOW, deprecated_last_timestamp=NOW - timedelta(hours=1))
    assert recency(event) == NOW


def test_legado_sem_event_time_usa_deprecated_last_timestamp():
    event = make_event(deprecated_last_timestamp=NOW)
    assert recency(event) == NOW


def test_sem_nenhum_timestamp_retorna_none():
    assert recency(make_event()) is None


# Contrato

def test_contrato_mapeia_campos_do_events_v1():
    event = make_event(uid="u-42", note="Failed to pull image", reason="Failed", namespace="teste-a", event_time=NOW)
    result = to_contract(event, NOW)
    assert result == {
        "uid": "u-42",
        "type": "Warning",
        "reason": "Failed",
        "message": "Failed to pull image",
        "namespace": "teste-a",
        "involved_object": {"kind": "Pod", "name": "nginx-abc", "namespace": "teste-a"},
        "timestamp": NOW.isoformat(),
    }
    assert datetime.fromisoformat(result["timestamp"]) == NOW


def test_recurso_cluster_scoped_tem_namespace_vazio():
    event = make_event(namespace="default", regarding={"kind": "Node", "name": "node-1"}, event_time=NOW)
    assert to_contract(event, NOW)["involved_object"]["namespace"] == ""


def test_timestamp_do_contrato_segue_a_precedencia():
    event = make_event(series_last_observed=NOW, event_time=NOW - timedelta(hours=1))
    [result] = select_events([event], watermark=None, overlap=INTERVAL)
    assert result["timestamp"] == NOW.isoformat()


# Janela

def test_startup_sem_marca_nao_filtra_por_recencia():
    old = make_event(uid="old", event_time=NOW - timedelta(minutes=40))
    assert [e["uid"] for e in select_events([old], watermark=None, overlap=INTERVAL)] == ["old"]


def test_evento_anterior_a_marca_menos_margem_e_descartado():
    old = make_event(uid="old", event_time=NOW - INTERVAL - timedelta(seconds=1))
    assert select_events([old], watermark=NOW, overlap=INTERVAL) == []


def test_evento_atrasado_dentro_da_margem_e_entregue():
    late = make_event(uid="late", event_time=NOW - timedelta(minutes=1))
    assert [e["uid"] for e in select_events([late], watermark=NOW, overlap=INTERVAL)] == ["late"]


def test_limite_da_janela_e_inclusivo():
    edge = make_event(uid="edge", deprecated_last_timestamp=NOW - INTERVAL)
    assert [e["uid"] for e in select_events([edge], watermark=NOW, overlap=INTERVAL)] == ["edge"]


def test_evento_recorrente_com_series_na_janela_e_entregue():
    event = make_event(uid="rec", series_last_observed=NOW, event_time=NOW - timedelta(hours=1))
    assert [e["uid"] for e in select_events([event], watermark=NOW, overlap=INTERVAL)] == ["rec"]


def test_evento_sem_timestamp_e_descartado_com_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert select_events([make_event(uid="sem-ts")], watermark=None, overlap=INTERVAL) == []
    assert "sem-ts" in caplog.text


def test_eventos_que_nao_sao_warning_sao_ignorados():
    normal = make_event(uid="n", type="Normal", event_time=NOW)
    warning = make_event(uid="w", event_time=NOW)
    assert [e["uid"] for e in select_events([normal, warning], watermark=None, overlap=INTERVAL)] == ["w"]
