import json
import logging
from pathlib import Path

import pytest

from my_agent_app.agents.verdict import parse_verdict
from my_agent_app.models.report import ReportStatus

FIXTURE = Path(__file__).parent / "fixtures" / "e2e_correction_responses.json"


def test_veredito_na_primeira_linha():
    assert parse_verdict("CORRIGIDO: imagem ajustada\n\n## Acoes Executadas") == ReportStatus.CORRIGIDO
    assert parse_verdict("FALHA: pod em CrashLoop\n\n## Acoes Executadas") == ReportStatus.FALHA_CORRECAO


def test_veredito_apos_prosa():
    text = "Analisei o deployment e apliquei o patch.\nTudo validado.\n\nCORRIGIDO: imagem ajustada\n"
    assert parse_verdict(text) == ReportStatus.CORRIGIDO


def test_vereditos_conflitantes_falha_vence():
    text = "FALHA: pod em CrashLoop\n...\nCORRIGIDO: imagem ajustada\n"
    assert parse_verdict(text) == ReportStatus.FALHA_CORRECAO


@pytest.mark.parametrize("line", [
    "**CORRIGIDO:** imagem ajustada",
    "**CORRIGIDO**: imagem ajustada",
    "__CORRIGIDO__: imagem ajustada",
    "- CORRIGIDO: imagem ajustada",
    "* CORRIGIDO: imagem ajustada",
    "# CORRIGIDO: imagem ajustada",
    "## **CORRIGIDO:** imagem ajustada",
    "> CORRIGIDO: imagem ajustada",
    "   CORRIGIDO: imagem ajustada",
])
def test_veredito_com_marcacao(line):
    assert parse_verdict(f"Resumo.\n{line}\n") == ReportStatus.CORRIGIDO


@pytest.mark.parametrize("line", ["**FALHA:** x", "- FALHA: x", "> FALHA: x", "### FALHA: x"])
def test_falha_com_marcacao(line):
    assert parse_verdict(f"CORRIGIDO: y\n{line}\n") == ReportStatus.FALHA_CORRECAO


def test_mencao_no_meio_de_frase_e_ignorada(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_verdict("o status CORRIGIDO: depende da validacao") == ReportStatus.FALHA_CORRECAO
    assert "sem linha de veredito" in caplog.text


def test_campos_do_formato_nao_contam_como_veredito():
    text = "## Acoes Executadas\n- **Status:** Corrigido\n## Resumo\n- Corrigidos: 1\n- Falhas: 0\n"
    assert parse_verdict(text) == ReportStatus.FALHA_CORRECAO


def test_limite_de_iteracoes_sem_veredito(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_verdict("Model call limits exceeded: run limit (25/25)") == ReportStatus.FALHA_CORRECAO
    assert "sem linha de veredito" in caplog.text


@pytest.mark.parametrize("text", ["", None])
def test_resposta_vazia(text, caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_verdict(text) == ReportStatus.FALHA_CORRECAO
    assert "sem linha de veredito" in caplog.text


def _recorded():
    if not FIXTURE.exists():
        return []
    return [pytest.param(c["response"], c["expected"], id=c["scenario"]) for c in json.loads(FIXTURE.read_text())]


@pytest.mark.parametrize("response, expected", _recorded())
def test_respostas_reais_do_e2e(response, expected):
    assert parse_verdict(response) == expected
