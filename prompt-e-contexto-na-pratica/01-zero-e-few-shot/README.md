# 01 — Zero-shot × few-shot: o que dois exemplos mudam

Duas chamadas lado a lado, na mesma tela. Mesma tarefa, mesmo modelo, mesmo
incidente. A única diferença é uma string a mais no prompt da direita.

À esquerda, **zero-shot**: papel e pedido, nenhum exemplo. À direita,
**few-shot**: o mesmo prompt com dois post-mortems de referência colados no
final.

A tela tem duas metades. Em cima, **o prompt exato de cada chamada** —
mensagem por mensagem, do jeito que sai para a API. Embaixo, o que voltou, com
o custo de cada uma.

## Como rodar

```bash
cp .env.example .env      # preencha ANTHROPIC_API_KEY
uv sync
uv run streamlit run src/app.py
```

> É o único exemplo da série com **dois painéis na mesma tela**: aqui a
> comparação é lado a lado, e lado a lado precisa de duas colunas.

## A tarefa, e por que ela é essa

Documentar um incidente encerrado como **post-mortem no padrão da equipe**.

A régua para escolher entre as duas técnicas é esta: **se o padrão é da empresa,
few-shot; se é do mercado, zero-shot provavelmente resolve.** Formato de
post-mortem é o caso clássico do primeiro grupo — cada time tem o seu, e não
existe um "correto" que o modelo possa saber de fora.

O que o painel da esquerda produz não é lixo. É um post-mortem competente, bem
escrito, com seções razoáveis — só que **não é o do seu time**. Ele inventa
"Impacto", "Lições aprendidas", às vezes um 5-Whys, e escreve as ações
corretivas em prosa. O da direita sai com as mesmas seções dos exemplos, na
mesma ordem, e com as ações no formato que o time usa de verdade:

```
- [ ] ação — @dono — até 2026-08-26
```

Essa é a parte incômoda da lição: **zero-shot erra parecendo certo**. Sem o
painel do lado, você aprovaria a resposta da esquerda sem pensar duas vezes.

## O prompt está na tela, e é o prompt de verdade

A metade de cima mostra o prompt que vai para o modelo, inteiro, com o tamanho
de cada um:

```
sem exemplos — zero-shot     com 2 exemplos — few-shot
o prompt — 986 caracteres    o prompt — 3683 caracteres
```

Aí está a lição antes de qualquer chamada: os dois pedidos são iguais, e a
diferença é o bloco de exemplos que só o da direita carrega. Few-shot não é uma
técnica de "pedir melhor" — é texto a mais no prompt, e dá para medir quanto.

O que está na tela é o prompt de verdade, não uma versão formatada para
exibição: a tela e o `invoke` leem da mesma função `mensagens()` em
`src/app.py`.

## O prompt não descreve o formato — de propósito

O `SYSTEM_PROMPT` em `src/app.py` tem duas linhas e diz só quem o modelo é.
Nenhuma seção, nenhum rótulo, nenhuma instrução de estrutura.

Isso é deliberado. Se o prompt descrevesse o formato, os exemplos não teriam o
que ensinar e os dois painéis sairiam parecidos — a comparação viraria teatro.
Todo o conhecimento do formato mora nos exemplos, em `src/postmortem.py`.

## Por que dois exemplos, e por que nessa ordem

Um exemplo só é one-shot. Dois é o mínimo que caracteriza few-shot, e para uma
tarefa de formato costuma ser suficiente. O sweet spot fica entre 2 e 5, com
retorno decrescente rápido: o salto grande é do zero para o primeiro.

As duas escolhas de desenho estão comentadas no `src/postmortem.py`, mas valem
aqui:

- **Causas diferentes** — certificado no primeiro, disco no segundo,
  configuração-como-código no alvo. Dois exemplos da mesma causa ensinariam o
  assunto em vez do formato.
- **O mais completo por último** — o modelo dá mais peso ao exemplo mais
  recente. O exemplo 2 é o que tem timeline longa, três ações corretivas e mais
  de um serviço envolvido.

E uma regra que não aparece no código porque é sobre o que **não** fazer: o
exemplo nunca pode ser o próprio alvo. Exemplo que é o gabarito não mede
generalização, mede memória.

## O readout, e onde few-shot dói

Cada painel abre com três números — **tokens de entrada**, **tokens de saída** e
**tempo** — e eles ficam no topo, não no rodapé, por um motivo prático: as duas
respostas têm tamanhos diferentes, então um rodapé cairia em alturas diferentes
nas duas colunas e não daria para comparar nada.

Lidos lado a lado, dizem a coisa toda. Os tokens de **saída** ficam parecidos:
as duas respostas têm mais ou menos o mesmo tamanho. Quem explode é a
**entrada** — os dois exemplos entram no prompt a cada chamada, e você paga por
eles todas as vezes.

É o custo oposto ao do [`02-chain-of-thought`](../02-chain-of-thought), onde
quem cresce é a saída, porque é lá que a deliberação acontece. Duas técnicas,
dois preços, dois lugares diferentes do readout.

## Arquivos

```
src/app.py         o system prompt, a montagem das mensagens, as duas chamadas e os readouts
src/postmortem.py  os dois exemplos, o incidente a documentar, e o desenho dos dois
.env.example       a chave da API e o modelo
pyproject.toml     as dependências, incluindo o streamlit
```
