import os

import streamlit as st
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, HumanMessage, SystemMessage

load_dotenv()

# Haiku de proposito: um modelo com menos reasoning torna o efeito de cada
# tecnica visivel na tela. Ver o CLAUDE.md da raiz antes de trocar.
model = init_chat_model(os.getenv("MODELO", "anthropic:claude-haiku-4-5-20251001"))

SYSTEM_PROMPT = """
Você é um assistente do time de operações. Responda de forma curta e direta.
"""

# A janela do Haiku 4.5: 200 mil tokens, e nem um a mais. E este teto que
# transforma "a janela e finita" de afirmacao em conta.
JANELA = 200_000


def nova_conversa() -> list:
    """Comeca do zero — so o system prompt na posicao 0."""
    return [SystemMessage(SYSTEM_PROMPT)]


def tokens_da_ultima_chamada(conversa: list) -> int:
    """O tamanho da conversa na ultima vez que ela foi enviada.

    Nao ha chamada nenhuma para "medir" a lista: o numero vem do recibo da
    ultima resposta. Antes da primeira pergunta nao existe recibo — e nao existe
    gasto.
    """
    for mensagem in reversed(conversa):
        if isinstance(mensagem, AIMessage):
            return mensagem.usage_metadata["input_tokens"]
    return 0


def mostrar(indice: int, mensagem) -> None:
    """Quanto da janela esta sendo gasto — e o assunto da aula na tela.

    O numero de entrada sobe a cada volta porque a conversa INTEIRA e reenviada
    toda vez. Nao e o modelo acumulando nada: e o seu codigo mandando de novo.
    """
    papel = "user" if isinstance(mensagem, HumanMessage) else "assistant"
    with st.chat_message(papel):
        st.markdown(mensagem.text)
        if isinstance(mensagem, AIMessage):
            # `indice + 1` e o tamanho que a lista tinha quando esta resposta
            # foi anexada: os mesmos 3, 5, 7… de uma volta para a outra.
            uso = mensagem.usage_metadata
            st.caption(
                f"[janela: {indice + 1} mensagens"
                f" · {uso['input_tokens']} tokens de entrada]"
            )


st.set_page_config(page_title="03 — o histórico como contexto", layout="wide")

st.title("03 — o histórico como contexto")
st.write(
    "O modelo não guarda nada entre uma chamada e outra. Quem lembra é a lista"
    " aqui do lado de cá, que o seu código reenvia inteira toda vez."
)

if "conversa" not in st.session_state:
    st.session_state.conversa = nova_conversa()

# O mesmo numero do rodape de cada resposta, agora contra o teto. Fica na barra
# lateral porque ele nao pertence a nenhuma volta: e o estado da conversa
# inteira, e precisa ficar parado num canto enquanto o chat rola.
with st.sidebar:
    st.subheader("A janela de contexto")

    acumular = st.checkbox("acumular o histórico", value=True)
    st.caption(
        "Desmarcado, a lista é zerada antes de cada pergunta: cada volta vai"
        " sozinha e o modelo esquece tudo. O medidor para de subir."
    )

    ocupado = tokens_da_ultima_chamada(st.session_state.conversa)
    st.progress(ocupado / JANELA)
    st.metric("ocupado na última chamada", f"{ocupado:,}".replace(",", "."))
    # Duas casas porque 200k e muito: com uma so, o numero fica cravado em
    # 100,0% a conversa inteira e a turma nao ve nada se mexer.
    st.metric("livre até 200k", f"{(JANELA - ocupado) / JANELA:.2%}".replace(".", ","))
    st.caption(f"mensagens na lista: {len(st.session_state.conversa)}")

if st.button("limpar — esquecer tudo"):
    st.session_state.conversa = nova_conversa()
    st.rerun()

# A posicao 0 e o system prompt: ele nao vira balao, mas continua na lista e
# continua sendo enviado. O indice do contador e o real, nao o do slice.
for indice, mensagem in enumerate(st.session_state.conversa[1:], start=1):
    mostrar(indice, mensagem)

pergunta = st.chat_input("Você:")

if pergunta:
    # Com a caixa desmarcada a lista e zerada antes da volta, e o que vai na
    # chamada e so a pergunta da vez. E o `limpar` acontecendo sozinho, toda vez.
    if not acumular:
        st.session_state.conversa = nova_conversa()

    # O contexto e isto: a pergunta entra na lista, e a lista inteira vai
    # junto na chamada. O modelo nao lembra de nada — quem lembra e a lista.
    st.session_state.conversa.append(HumanMessage(pergunta))
    mostrar(len(st.session_state.conversa) - 1, st.session_state.conversa[-1])

    with st.spinner("chamando o modelo…"):
        resposta = model.invoke(st.session_state.conversa)

    # A barra lateral ja foi desenhada la em cima, com o numero de antes desta
    # resposta. O rerun redesenha a tela inteira a partir da lista — que e,
    # afinal, o unico lugar onde a conversa existe.
    st.session_state.conversa.append(resposta)
    st.rerun()
