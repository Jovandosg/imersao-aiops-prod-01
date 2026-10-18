import markdown
from markdown.extensions import Extension
from markupsafe import Markup


class EscapeHtml(Extension):
    """Sem o parse de HTML cru, o serializer da lib o escapa: `<none>` do kubectl aparece como texto."""

    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")


def render_markdown(text: str) -> Markup:
    return Markup(markdown.markdown(text, extensions=["fenced_code", "tables", EscapeHtml()]))
