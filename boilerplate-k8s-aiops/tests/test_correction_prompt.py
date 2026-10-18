from my_agent_app.agents.correction_prompt import build_correction_prompt

REPORT = """\
# Imagem inexistente no deployment nginx

### Comando Sugerido
kubectl patch deployment nginx -n teste-a --type=strategic -p '{"spec":{"template":{}}}'
"""


def test_markdown_do_relatorio_injetado_sem_marcador():
    prompt = build_correction_prompt(REPORT)
    assert REPORT in prompt
    assert "{report_markdown}" not in prompt


def test_prompt_mantem_regras_e_formato_do_veredito():
    prompt = build_correction_prompt(REPORT)
    assert "NUNCA delete namespaces, PersistentVolumeClaims ou recursos em kube-system." in prompt
    assert "NUNCA use merge patch simples sobre a lista `containers`" in prompt
    assert "se a SUA propria correcao introduzir um novo erro" in prompt
    assert "- CORRIGIDO: [resumo de uma linha]" in prompt
    assert "- FALHA: [resumo de uma linha]" in prompt
    assert "## Acoes Executadas" in prompt
