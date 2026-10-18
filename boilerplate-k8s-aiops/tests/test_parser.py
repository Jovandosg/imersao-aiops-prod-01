import json
import logging
from pathlib import Path

from my_agent_app.agents.parser import parse_report
from my_agent_app.models.report import ReportStatus

TWO_PROBLEMS = """\
# Relatorio de Diagnostico Kubernetes

## Resumo
| Total | Criticos | Altos | Medios | Baixos |
|-------|----------|-------|--------|--------|
| 2     | 1        | 1     | 0      | 0      |

---

## Problema 1: Imagem inexistente
- **Severidade:** CRITICO
- **Namespace:** teste-a
- **Recursos Afetados:** pod/nginx-abc, deployment/nginx
- **Eventos:** u1, u2
- **Conclusao:** conclusiva

### Causa Raiz
A imagem `ngin:latest` nao existe.

### Solucao Recomendada
Corrigir para `nginx:latest`.

---

## Problema 2: Senha do banco divergente
- **Severidade:** ALTO
- **Namespace:** `teste-b`
- **Recursos Afetados:** deployment/kubenews
- **Eventos:** `u3`
- **Conclusão:** inconclusiva

### Causa Raiz
Falha de autenticacao no banco.
"""


def test_dois_problemas_independentes():
    first, second = parse_report(TWO_PROBLEMS, ["u1", "u2", "u3"])

    assert (first.title, first.severity, first.status, first.namespace, first.event_uids) == (
        "Imagem inexistente", "CRITICO", ReportStatus.COMPLETO, "teste-a", ["u1", "u2"]
    )
    assert (second.title, second.severity, second.status, second.namespace, second.event_uids) == (
        "Senha do banco divergente", "ALTO", ReportStatus.INCOMPLETO, "teste-b", ["u3"]
    )


def test_cabecalho_promovido_e_resumo_descartado():
    first, second = parse_report(TWO_PROBLEMS, ["u1", "u2", "u3"])

    assert first.markdown.startswith("# Imagem inexistente\n- **Severidade:** CRITICO")
    assert "Resumo" not in first.markdown and "| Total" not in first.markdown
    assert "Problema 2" not in first.markdown
    assert not first.markdown.rstrip().endswith("---")
    assert second.markdown.startswith("# Senha do banco divergente\n")
    assert "Resumo" not in second.markdown


def test_severidade_e_conclusao_ausentes(caplog):
    text = "## Problema 1: Algo\n- **Namespace:** ns\n- **Eventos:** u1\n"
    with caplog.at_level(logging.WARNING):
        [problem] = parse_report(text, ["u1"])
    assert problem.severity is None
    assert problem.status == ReportStatus.COMPLETO
    assert "severidade" in caplog.text
    assert "conclusao" in caplog.text


def test_severidade_desconhecida_vira_nula(caplog):
    text = "## Problema 1: Algo\n- **Severidade:** GRAVISSIMO\n- **Eventos:** u1\n- **Conclusao:** conclusiva\n"
    with caplog.at_level(logging.WARNING):
        [problem] = parse_report(text, ["u1"])
    assert problem.severity is None
    assert "GRAVISSIMO" in caplog.text


def test_severidade_com_acento_e_caixa_baixa():
    text = "## Problema 1: Algo\n- **severidade:** Crítico\n- **Eventos:** u1\n- **Conclusao:** conclusiva\n"
    [problem] = parse_report(text, ["u1"])
    assert problem.severity == "CRITICO"


def test_uid_estranho_e_uid_duplicado(caplog):
    text = (
        "## Problema 1: A\n- **Severidade:** ALTO\n- **Eventos:** u1, intruso\n- **Conclusao:** conclusiva\n\n"
        "## Problema 2: B\n- **Severidade:** BAIXO\n- **Eventos:** u1, u2\n- **Conclusao:** conclusiva\n"
    )
    with caplog.at_level(logging.WARNING):
        first, second = parse_report(text, ["u1", "u2"])
    assert first.event_uids == ["u1"]
    assert second.event_uids == ["u2"]
    assert "intruso" in caplog.text
    assert "mais de um problema" in caplog.text


def test_uid_do_lote_nao_citado_gera_warning(caplog):
    text = "## Problema 1: A\n- **Severidade:** ALTO\n- **Eventos:** u1\n- **Conclusao:** conclusiva\n"
    with caplog.at_level(logging.WARNING):
        parse_report(text, ["u1", "esquecido"])
    assert "esquecido" in caplog.text


def test_problema_sem_uid_valido_fica_com_lista_vazia(caplog):
    text = "## Problema 1: A\n- **Severidade:** ALTO\n- **Eventos:** intruso\n- **Conclusao:** conclusiva\n"
    with caplog.at_level(logging.WARNING):
        [problem] = parse_report(text, ["u1"])
    assert problem.event_uids == []
    assert "sem nenhum uid" in caplog.text


def test_resposta_vazia_ou_sem_problemas():
    assert parse_report("", ["u1"]) == []
    assert parse_report("# Relatorio\n\nNao consegui investigar.", ["u1"]) == []


def test_resposta_real_capturada_no_e2e(caplog):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "e2e_agent_response.json").read_text())
    events = {e["uid"]: e for e in fixture["events"]}

    with caplog.at_level(logging.WARNING):
        problems = parse_report(fixture["response"], list(events))

    assert len(problems) == 2
    by_namespace = {p.namespace: p for p in problems}
    nginx, kubenews = by_namespace["teste-a"], by_namespace["teste-b"]
    assert nginx.status == kubenews.status == ReportStatus.COMPLETO
    assert nginx.severity == kubenews.severity == "CRITICO"
    assert "ngin:latest" in nginx.markdown
    assert "DB_PASSWORD" in kubenews.markdown
    assert all(events[u]["namespace"] == "teste-a" for u in nginx.event_uids)
    assert all(events[u]["namespace"] == "teste-b" for u in kubenews.event_uids)
    # O modelo repetiu um uid do nginx no Problema 2: fica so no primeiro
    assert "mais de um problema" in caplog.text
    assert set(nginx.event_uids) | set(kubenews.event_uids) == set(events)
    assert not nginx.markdown.startswith("Perfeito")
