from markupsafe import Markup

from my_agent_app.web.rendering import render_markdown


def test_html_embutido_e_escapado():
    html = render_markdown("NAME  READY  NOMINATED NODE <none>\n\n<script>alert(1)</script>\n")
    assert "&lt;none&gt;" in html
    assert "<none>" not in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_retorna_markup():
    assert isinstance(render_markdown("# x"), Markup)


def test_tabela_renderiza():
    html = render_markdown("| Total | Criticos |\n|-------|----------|\n| 1     | 1        |\n")
    assert "<table>" in html
    assert "<td>1</td>" in html


def test_bloco_de_codigo_cercado_renderiza_e_escapa():
    html = render_markdown("```\nkubectl get pods\nNOMINATED NODE <none>\n```\n")
    assert "<pre><code>" in html
    assert "kubectl get pods" in html
    assert "&lt;none&gt;" in html


def test_markdown_malformado_nao_levanta():
    html = render_markdown("```\nbloco sem fechamento\n**negrito sem fechar\n| a | b\n")
    assert "bloco sem fechamento" in html
