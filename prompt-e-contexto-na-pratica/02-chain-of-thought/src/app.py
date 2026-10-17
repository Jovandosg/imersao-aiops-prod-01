import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage

# Import de irmao, e nao `from src.evidencia import ...`: o streamlit executa o
# `src/app.py` direto, entao quem entra no sys.path e a pasta `src/`, nao a raiz
# do projeto.
from evidencia import EVIDENCIA

load_dotenv()

# Haiku de proposito: um modelo com menos reasoning torna o efeito de cada
# tecnica visivel na tela. Ver o CLAUDE.md da raiz antes de trocar.
model = init_chat_model(os.getenv("MODELO", "anthropic:claude-haiku-4-5-20251001"))


# A unica diferenca de forma para o `01` esta neste bloco: alem do papel e do
# formato, o prompt entrega um PERCURSO. Nao e pedir "pense bem" — e nomear as
# etapas do raciocinio e obrigar cada uma a aparecer na resposta.
SYSTEM_PROMPT = """
Você trabalha no time de operações e investiga incidentes em produção.

Antes de concluir qualquer coisa, percorra o raciocínio em voz alta, nesta ordem:

1. O que você observa — os fatos da evidência, sem interpretação
2. O que isso descarta — cada hipótese eliminada, com o dado que a elimina
3. O que sobra como hipótese — a causa mais provável e por que ela sobrevive
4. O que checar para confirmar — o dado que você ainda não tem

Só depois de percorrer as quatro etapas, escreva a conclusão em uma frase.

Não pule etapa e não antecipe a conclusão. Se a evidência não sustentar uma
causa única, diga isso em vez de escolher a mais provável.
"""


def mensagens() -> list:
    """O que vai para o modelo.

    A tela e o `invoke` leem os dois daqui, de proposito: a turma nunca pode
    ver uma coisa e o modelo receber outra.
    """
    return [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(f"Diagnostique o incidente abaixo.\n{EVIDENCIA}"),
    ]


def prompt_na_tela() -> str:
    """O prompt inteiro, como um texto so.

    A turma ainda nao viu o array de mensagens — isso e assunto do 03. Aqui e
    "o prompt", e ponto. Note que o texto sai das mesmas mensagens que o
    `invoke` recebe, nao de uma copia montada para exibicao.
    """
    return "\n".join(mensagem.text for mensagem in mensagens())


st.set_page_config(page_title="02 — chain-of-thought", layout="wide")

st.title("02 — chain-of-thought")
st.write(
    "Um prompt, uma chamada. A diferença é que aqui o prompt entrega um percurso"
    " de raciocínio — e a deliberação acontece na saída."
)

st.divider()
st.header("O que vai ser executado")

prompt = prompt_na_tela()
st.caption(f"o prompt — {len(prompt)} caracteres")
st.code(prompt, language="markdown", height=420, wrap_lines=True)

st.divider()

if st.button("Diagnosticar o incidente", type="primary"):
    st.header("O que voltou")

    inicio = time.perf_counter()
    with st.spinner("chamando o modelo…"):
        resposta = model.invoke(mensagens())
    segundos = time.perf_counter() - inicio

    # Os mesmos tres numeros do `01`, e o preco vem antes do texto. Aqui quem
    # cresce e a SAIDA: e nela que a deliberacao acontece. No `01` cresce a
    # entrada, porque os exemplos entram no prompt toda chamada.
    uso = resposta.usage_metadata
    entrada, saida, tempo = st.columns(3)
    entrada.metric("tokens de entrada", uso["input_tokens"])
    saida.metric("tokens de saída", uso["output_tokens"])
    tempo.metric("tempo", f"{segundos:.1f}s")

    st.markdown(resposta.text)
