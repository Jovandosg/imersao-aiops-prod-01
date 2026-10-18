import logging

import pytest

from my_agent_app.collector.config import DEFAULT_INTERVAL_MINUTES, get_interval_minutes


def test_sem_variavel_usa_padrao(monkeypatch):
    monkeypatch.delenv("EVENT_COLLECTION_INTERVAL_MINUTES", raising=False)
    assert get_interval_minutes() == DEFAULT_INTERVAL_MINUTES == 3


def test_valor_fracionario_e_aceito(monkeypatch):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", "0.5")
    assert get_interval_minutes() == 0.5


@pytest.mark.parametrize("raw", ["abc", "0", "-2", "", "nan", "inf"])
def test_valor_invalido_cai_no_padrao_com_warning(monkeypatch, caplog, raw):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", raw)
    with caplog.at_level(logging.WARNING):
        assert get_interval_minutes() == 3
    assert "EVENT_COLLECTION_INTERVAL_MINUTES" in caplog.text
