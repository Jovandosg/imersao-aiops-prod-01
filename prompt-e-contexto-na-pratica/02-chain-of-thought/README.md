# 02 — Chain-of-thought: o raciocínio explícito

A mesma estrutura de sempre — um `invoke`, uma resposta, na mesma interface do
[`01`](../01-zero-e-few-shot). A diferença em relação a ele cabe num bloco do
`SYSTEM_PROMPT`.

## Como rodar

```bash
cp .env.example .env      # preencha ANTHROPIC_API_KEY
uv sync
uv run streamlit run src/app.py
```

## O que muda em relação ao `01`

O prompt deixa de pedir só o formato e passa a entregar um **percurso**:

```
1. O que você observa
2. O que isso descarta
3. O que sobra como hipótese
4. O que checar para confirmar
```

Não é "pense bem" nem "seja cuidadoso". É nomear as etapas do raciocínio e
obrigar cada uma a aparecer na resposta. O modelo passa a ter onde deliberar
antes de concluir — e a deliberação ocupa tokens de saída, que é onde ela
acontece.

## A tarefa, e por que ela é essa

Um incidente com **hipóteses concorrentes de verdade**. A evidência está em
`src/evidencia.py`, separada porque é longa, e foi desenhada com três
propriedades:

1. **Mais de uma causa é plausível** — memória, CPU e banco competem
2. **Há o que descartar** — memória e CPU aparecem estáveis de propósito; são os
   ramos que o raciocínio explícito precisa podar
3. **O dado que fecha o diagnóstico não está lá** — o limite de conexões do
   banco compartilhado fica de fora

O item 3 é deliberado. Uma boa resposta aqui termina na etapa 4 dizendo o que
falta checar — e quem entrega esse dado é o exemplo
[`04-contexto-de-documento`](../04-contexto-de-documento), pelo documento
interno do projeto.
Os dois lados da série se encontram ali.

## Raciocínio explícito como custo

Compare o readout com o do `01`: são as mesmas três métricas na tela nos dois
exemplos — tokens de entrada, tokens de saída e tempo. Aqui quem cresce são os
tokens de **saída** e o tempo, porque é na saída que a deliberação acontece. É
o preço da técnica, e ele é real — motivo pelo qual ela não se aplica a toda
tarefa. Numa tarefa de formato como a do `01`, esse gasto não compra nada; lá o
preço é outro, e ele aparece na **entrada**.

## O modelo importa aqui

Estes exemplos rodam em Haiku de propósito. Num modelo maior o zero-shot já
chega perto sozinho e o contraste some da tela. Ver o `CLAUDE.md` da raiz.

## Arquivos

```
src/app.py         o app Streamlit: o percurso no prompt, o invoke e o readout
src/evidencia.py   a evidência do incidente, e o porquê de cada peça dela
.env.example       a chave da API e o modelo
pyproject.toml     as dependências
```
