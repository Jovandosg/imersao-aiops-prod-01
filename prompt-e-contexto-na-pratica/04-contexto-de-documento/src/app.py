import os

import streamlit as st
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, HumanMessage, SystemMessage

load_dotenv()

# Haiku de proposito: um modelo com menos reasoning torna o efeito de cada
# tecnica visivel na tela. Ver o CLAUDE.md da raiz antes de trocar.
model = init_chat_model(os.getenv("MODELO", "anthropic:claude-haiku-4-5-20251001"))

# A janela do Haiku 4.5: 200 mil tokens, e nem um a mais. E este teto que
# transforma "a janela e finita" de afirmacao em conta.
JANELA = 200_000

SYSTEM_PROMPT = """
Você é um assistente do time de operações. Responda de forma curta e direta.

Você pode ter recebido documentos internos. Responda com base neles sempre que
cobrirem a pergunta, e diga de qual documento tirou cada informação. Se os
documentos não cobrirem — ou se não houver documento nenhum —, diga isso em vez
de completar com o que costuma ser verdade em outros lugares.
"""


def nova_conversa(documentos: list) -> list:
    """A unica diferenca para o `03` esta aqui.

    Cada documento entra como uma mensagem no comeco da lista, uma vez, e passa
    a viajar junto em todas as chamadas seguintes — exatamente como o historico.
    Contexto e contexto: nao ha mecanismo especial para "anexar arquivo", ha
    texto entrando na janela.

    Sem documento nenhum a lista comeca igualzinha a do `03` — e o app responde
    igual ao `03`, que e o comeco da demonstracao.
    """
    return [SystemMessage(SYSTEM_PROMPT)] + [
        HumanMessage(f"Documento interno de referência — {nome}:\n\n{texto}")
        for nome, texto in documentos
    ]


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
    """Quanto da janela esta sendo gasto — e o assunto da aula na tela."""
    papel = "user" if isinstance(mensagem, HumanMessage) else "assistant"
    with st.chat_message(papel):
        st.markdown(mensagem.text)
        if isinstance(mensagem, AIMessage):
            uso = mensagem.usage_metadata
            st.caption(
                f"[janela: {indice + 1} mensagens"
                f" · {uso['input_tokens']} tokens de entrada]"
            )


st.set_page_config(page_title="04 — o documento em contexto", layout="wide")

st.title("04 — o documento em contexto")
st.write(
    "Começa vazio: sem documento, este é o chat do 03 e o modelo adivinha. Carregue"
    " um arquivo na barra lateral e ele passa a viajar na janela, como qualquer"
    " outra mensagem."
)

with st.sidebar:
    st.subheader("A janela de contexto")

    enviados = st.file_uploader(
        "documentos no contexto",
        type=["md", "txt"],
        accept_multiple_files=True,
    )
    st.caption(
        "Arraste os arquivos da pasta `contexto/` — o documento do projeto, os"
        " incidentes, ou qualquer `.md` seu. Cada um vira uma mensagem no"
        " começo da lista."
    )

# Ler aqui, e nao dentro do `nova_conversa`, para o tamanho aparecer na tela
# mesmo antes da primeira pergunta.
documentos = [(f.name, f.getvalue().decode("utf-8")) for f in enviados]

# Trocar o que esta no contexto refaz a conversa: os documentos moram no comeco
# da lista, entao nao ha como trocar um sem remontar a lista inteira. E honesto
# e e uma linha — documento nao e "anexo", e posicao.
if st.session_state.get("documentos") != [nome for nome, _ in documentos]:
    st.session_state.documentos = [nome for nome, _ in documentos]
    st.session_state.conversa = nova_conversa(documentos)

with st.sidebar:
    # O mesmo numero do rodape de cada resposta, agora contra o teto.
    ocupado = tokens_da_ultima_chamada(st.session_state.conversa)
    st.progress(ocupado / JANELA)
    st.metric("ocupado na última chamada", f"{ocupado:,}".replace(",", "."))
    # Duas casas porque 200k e muito: com uma so, o numero fica cravado em
    # 100,0% a conversa inteira e a turma nao ve nada se mexer.
    st.metric("livre até 200k", f"{(JANELA - ocupado) / JANELA:.2%}".replace(".", ","))
    st.caption(f"mensagens na lista: {len(st.session_state.conversa)}")

for nome, texto in documentos:
    with st.expander(f"documento: {nome} · {len(texto)} caracteres"):
        st.markdown(texto)

# O prefixo e o system prompt mais um documento cada: nenhum deles vira balao,
# mas todos continuam na lista e continuam sendo enviados — e e por isso que a
# primeira pergunta aqui ja custa mais que a do `03`. O indice do contador e o
# real, nao o do slice.
prefixo = len(documentos) + 1
for indice, mensagem in enumerate(st.session_state.conversa[prefixo:], start=prefixo):
    mostrar(indice, mensagem)

pergunta = st.chat_input("Você:")

if pergunta:
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
