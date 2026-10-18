import logging

import pytest

from my_agent_app.agents.config import (
    get_agent_max_iterations,
    get_agent_model_name,
    get_correction_max_iterations,
    get_correction_model_name,
    get_correction_timeout_minutes,
    get_mcp_server_url,
    get_retry_cooldown_minutes,
    get_stale_timeout_minutes,
)

MINUTE_VARS = [
    ("ANALYSIS_RETRY_COOLDOWN_MINUTES", get_retry_cooldown_minutes),
    ("ANALYSIS_STALE_TIMEOUT_MINUTES", get_stale_timeout_minutes),
]


def test_modelo_padrao_e_haiku(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL_NAME", raising=False)
    assert get_agent_model_name() == "claude-haiku-4-5"


def test_modelo_configurado(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "claude-sonnet-4-5")
    assert get_agent_model_name() == "claude-sonnet-4-5"


def test_mcp_url_padrao(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert get_mcp_server_url() == "http://localhost:3001/mcp"


def test_max_iterations_padrao(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ITERATIONS", raising=False)
    assert get_agent_max_iterations() == 25


def test_max_iterations_configurado(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "10")
    assert get_agent_max_iterations() == 10


@pytest.mark.parametrize("raw", ["0", "-3", "abc", "2.5", ""])
def test_max_iterations_invalido_cai_no_padrao_com_warning(monkeypatch, caplog, raw):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", raw)
    with caplog.at_level(logging.WARNING):
        assert get_agent_max_iterations() == 25
    assert "AGENT_MAX_ITERATIONS" in caplog.text


@pytest.mark.parametrize("name, getter", MINUTE_VARS)
def test_minutos_padrao(monkeypatch, name, getter):
    monkeypatch.delenv(name, raising=False)
    assert getter() == 30


@pytest.mark.parametrize("name, getter", MINUTE_VARS)
def test_minutos_fracionario_e_aceito(monkeypatch, name, getter):
    monkeypatch.setenv(name, "0.5")
    assert getter() == 0.5


@pytest.mark.parametrize("raw", ["abc", "0", "-2", "", "nan", "inf"])
@pytest.mark.parametrize("name, getter", MINUTE_VARS)
def test_minutos_invalido_cai_no_padrao_com_warning(monkeypatch, caplog, name, getter, raw):
    monkeypatch.setenv(name, raw)
    with caplog.at_level(logging.WARNING):
        assert getter() == 30
    assert name in caplog.text


def test_modelo_da_correcao_configurado(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_NAME", "claude-haiku-4-5")
    monkeypatch.setenv("CORRECTION_MODEL_NAME", "claude-sonnet-4-5")
    assert get_correction_model_name() == "claude-sonnet-4-5"


@pytest.mark.parametrize("raw", [None, ""])
def test_modelo_da_correcao_cai_no_modelo_da_analise(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("CORRECTION_MODEL_NAME", raising=False)
    else:
        monkeypatch.setenv("CORRECTION_MODEL_NAME", raw)
    monkeypatch.setenv("AGENT_MODEL_NAME", "claude-sonnet-4-5")
    assert get_correction_model_name() == "claude-sonnet-4-5"


def test_modelo_da_correcao_padrao(monkeypatch):
    monkeypatch.delenv("CORRECTION_MODEL_NAME", raising=False)
    monkeypatch.delenv("AGENT_MODEL_NAME", raising=False)
    assert get_correction_model_name() == "claude-haiku-4-5"


def test_correction_max_iterations_padrao_e_configurado(monkeypatch):
    monkeypatch.delenv("CORRECTION_MAX_ITERATIONS", raising=False)
    assert get_correction_max_iterations() == 25
    monkeypatch.setenv("CORRECTION_MAX_ITERATIONS", "40")
    assert get_correction_max_iterations() == 40


@pytest.mark.parametrize("raw", ["0", "-3", "abc", "2.5", ""])
def test_correction_max_iterations_invalido_cai_no_padrao_com_warning(monkeypatch, caplog, raw):
    monkeypatch.setenv("CORRECTION_MAX_ITERATIONS", raw)
    with caplog.at_level(logging.WARNING):
        assert get_correction_max_iterations() == 25
    assert "CORRECTION_MAX_ITERATIONS" in caplog.text


def test_correction_timeout_padrao_e_fracionario(monkeypatch):
    monkeypatch.delenv("CORRECTION_TIMEOUT_MINUTES", raising=False)
    assert get_correction_timeout_minutes() == 10
    monkeypatch.setenv("CORRECTION_TIMEOUT_MINUTES", "0.5")
    assert get_correction_timeout_minutes() == 0.5


@pytest.mark.parametrize("raw", ["abc", "0", "-2", "", "nan", "inf"])
def test_correction_timeout_invalido_cai_no_padrao_com_warning(monkeypatch, caplog, raw):
    monkeypatch.setenv("CORRECTION_TIMEOUT_MINUTES", raw)
    with caplog.at_level(logging.WARNING):
        assert get_correction_timeout_minutes() == 10
    assert "CORRECTION_TIMEOUT_MINUTES" in caplog.text
