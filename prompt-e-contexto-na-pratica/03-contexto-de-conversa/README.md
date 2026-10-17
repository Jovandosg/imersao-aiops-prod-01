# 03 — O histórico como contexto

Um chat no browser. A lição não é "o chat tem memória" — é o contrário: **o
modelo não guarda nada entre uma chamada e outra.** Quem lembra é o seu código,
reenviando a conversa inteira toda vez.

## Como rodar

```bash
cp .env.example .env      # preencha ANTHROPIC_API_KEY
uv sync
uv run streamlit run src/app.py
```

O botão `limpar — esquecer tudo` zera a conversa. Na barra lateral fica o
medidor da janela, e com ele o checkbox `acumular o histórico`.

## O contexto é um array

Tudo que existe de "memória" aqui está em três linhas de `src/app.py`:

```python
st.session_state.conversa.append(HumanMessage(pergunta))
resposta = model.invoke(st.session_state.conversa)   # a lista INTEIRA vai junto
st.session_state.conversa.append(resposta)
```

O `invoke` recebe a lista completa, não a última pergunta. Não há estado do
lado do modelo — há uma lista do lado de cá que cresce e é reenviada.

## A prova é o botão `limpar`

1. Pergunte algo
2. Faça uma pergunta de acompanhamento que só faz sentido com a anterior —
   funciona
3. Clique em `limpar`
4. Repita a pergunta de acompanhamento — ela se perde

Apagou a lista, esqueceu. Não havia mais nada além dela.

## A janela na tela

Embaixo de cada resposta aparece quantas mensagens e quantos **tokens de
entrada** foram enviados — as respostas anteriores continuam na tela, então dá
para ver a série inteira crescendo. Esse número sobe sempre, e é o assunto da
aula ficando visível: a janela é finita, o histórico ocupa espaço nela, e o que
você deixa acumular é o que você está pagando para reenviar.

A barra lateral pega esse mesmo número e coloca contra o teto: **200 mil
tokens**, a janela do Haiku 4.5. É lá que se vê quanto ainda cabe — e a resposta
honesta, numa conversa de aula, é "quase tudo". O ponto não é assustar com a
barra cheia; é dar escala ao que o contador mostra volta a volta.

Três limites, de propósito não resolvidos aqui: a conversa morre ao fechar, é
uma conversa só, e cresce sem freio até bater na janela.

## O interruptor

O checkbox `acumular o histórico` liga e desliga a lista. Desmarcado, ela é
zerada antes de cada pergunta: cada volta vai sozinha, o medidor para de subir —
e chega a **descer**, porque a chamada ficou menor — e o modelo passa a não
saber nada do que foi dito duas linhas acima.

É a mesma prova do `limpar`, num clique só. Um apaga o passado; o outro desliga
o futuro.

## O que falta

Nada do que está nessa conversa veio de fora. O que muda quando você coloca
material que o modelo não teria como saber está no exemplo seguinte,
[`04-contexto-de-documento`](../04-contexto-de-documento) — que é este mesmo
chat, com o mesmo `nova_conversa`, o mesmo `append` e o mesmo `invoke`. O que
muda é o que já está na lista quando você faz a primeira pergunta.

## Arquivos

```
src/app.py        o chat, a lista reenviada, o contador e o medidor da janela
.env.example      a chave da API e o modelo
pyproject.toml    as dependências
```
