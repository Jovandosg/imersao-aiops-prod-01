import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage

# Import de irmao, e nao `from src.postmortem import ...` como no 02: o
# streamlit executa o `src/app.py` direto, entao quem entra no sys.path e a
# pasta `src/`, nao a raiz do projeto.
from postmortem import EXEMPLOS, INCIDENTE

load_dotenv()

# Haiku de proposito: um modelo com menos reasoning torna o efeito de cada
# tecnica visivel na tela. Ver o CLAUDE.md da raiz antes de trocar.
model = init_chat_model(os.getenv("MODELO", "anthropic:claude-haiku-4-5-20251001"))


# Papel, e mais nada. O prompt NAO descreve as secoes do post-mortem, de
# proposito: se descrevesse, os exemplos nao teriam o que ensinar e a
# comparacao entre os dois paineis seria desonesta.
SYSTEM_PROMPT = """
Você trabalha no time de operações e documenta incidentes já encerrados como
post-mortem.
"""

PEDIDO = f"Documente o incidente abaixo como post-mortem.\n{INCIDENTE}"


def mensagens(exemplos: str) -> list:
    """O que vai para o modelo.

    A tela e o `invoke` leem os dois daqui, de proposito: a turma nunca pode
    ver uma coisa e o modelo receber outra.
    """
    return [SystemMessage(SYSTEM_PROMPT + exemplos), HumanMessage(PEDIDO)]


def prompt_na_tela(exemplos: str) -> str:
    """O prompt inteiro, como um texto so.

    A turma ainda nao viu o array de mensagens — isso e assunto do 03. Aqui e
    "o prompt", e ponto. Note que o texto sai das mesmas mensagens que o
    `invoke` recebe, nao de uma copia montada para exibicao.
    """
    return "\n".join(mensagem.text for mensagem in mensagens(exemplos))


def mostrar_prompt(coluna, titulo: str, exemplos: str) -> None:
    """O prompt exato desta chamada, antes de ela acontecer."""
    with coluna:
        st.subheader(titulo)
        prompt = prompt_na_tela(exemplos)
        st.caption(f"o prompt — {len(prompt)} caracteres")
        st.code(prompt, language="markdown", height=420, wrap_lines=True)


def mostrar_resposta(coluna, titulo: str, exemplos: str) -> None:
    """Uma chamada: o preco em cima, a resposta embaixo.

    O preco vem ANTES do texto de proposito. As duas respostas tem tamanhos
    diferentes, entao um rodape ficaria em alturas diferentes nas duas colunas
    e nao daria para comparar nada. No topo, os numeros ficam lado a lado.
    """
    with coluna:
        st.subheader(titulo)

        inicio = time.perf_counter()
        with st.spinner("chamando o modelo…"):
            resposta = model.invoke(mensagens(exemplos))
        segundos = time.perf_counter() - inicio

        uso = resposta.usage_metadata
        entrada, saida, tempo = st.columns(3)
        entrada.metric("tokens de entrada", uso["input_tokens"])
        saida.metric("tokens de saída", uso["output_tokens"])
        tempo.metric("tempo", f"{segundos:.1f}s")

        st.markdown(resposta.text)


st.set_page_config(page_title="01 — zero-shot × few-shot", layout="wide")

st.title("01 — zero-shot × few-shot")
st.write(
    "A mesma tarefa, o mesmo modelo, duas chamadas. A única diferença entre elas"
    " é um pedaço a mais no prompt da direita."
)

st.divider()
st.header("O que vai ser executado")

esquerda, direita = st.columns(2)
mostrar_prompt(esquerda, "sem exemplos — zero-shot", "")
mostrar_prompt(direita, "com 2 exemplos — few-shot", EXEMPLOS)

st.divider()

if st.button("Rodar as duas chamadas", type="primary"):
    st.header("O que voltou")

    esquerda, direita = st.columns(2)
    mostrar_resposta(esquerda, "sem exemplos — zero-shot", "")
    mostrar_resposta(direita, "com 2 exemplos — few-shot", EXEMPLOS)
