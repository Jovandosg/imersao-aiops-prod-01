# Engenharia de prompt e engenharia de contexto — exemplos em Python

Quatro exemplos usados nas aulas de **engenharia de prompt** e **engenharia de
contexto**. Eles não pertencem a uma turma específica: aparecem em imersões,
cursos e treinamentos diferentes, sempre com a mesma função — mostrar cada
técnica acontecendo na tela.

Este é um **projeto didático** do [veronez.io](https://veronez.io/): o código
existe para ser lido em aula, não para rodar em produção.

São quatro projetos independentes. Você pode clonar o repositório inteiro e
rodar só o que interessa — cada pasta tem seu próprio `pyproject.toml` e roda
sozinha.

> **Acompanhar é opcional.** Nada aqui é checkpoint de aula. A execução é
> conduzida na tela; o código fica com você e roda depois, com calma.

## Os exemplos

| # | Pasta | Aula | O que ensina |
|---|---|---|---|
| 01 | [`01-zero-e-few-shot`](01-zero-e-few-shot) | prompt | Zero-shot e few-shot lado a lado, na mesma tarefa: o que dois exemplos no prompt mudam — e o que eles custam na entrada |
| 02 | [`02-chain-of-thought`](02-chain-of-thought) | prompt | Raciocínio explícito como **recurso** (diagnóstico com hipóteses concorrentes) e como **custo** (mais token, mais latência) |
| 03 | [`03-contexto-de-conversa`](03-contexto-de-conversa) | contexto | O histórico é um array que o **seu código** reenvia. O modelo não lembra de nada |
| 04 | [`04-contexto-de-documento`](04-contexto-de-documento) | contexto | Um documento lido em runtime entra na janela como qualquer mensagem — e a saída deixa de adivinhar |

Eles funcionam **em pares**. O `01` e o `02` são as aulas de prompt: o `01`
compara zero-shot e few-shot na mesma tarefa, e o `02` traz o chain-of-thought
numa tarefa que exige raciocínio. O `03` e o `04` são o mesmo chat, e a
diferença entre os dois é o documento.

Há também um fio ligando os pares: o diagnóstico do `02` termina dizendo qual
dado falta, e é o documento do `04` que entrega esse dado.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) — gerencia Python e dependências
- Python 3.12 (o `uv` instala sozinho, se faltar)
- Uma chave da API da Anthropic ([console.anthropic.com](https://console.anthropic.com))

## Como rodar qualquer exemplo

Sempre **de dentro da pasta do exemplo**:

```bash
cd 01-zero-e-few-shot
cp .env.example .env      # preencha ANTHROPIC_API_KEY
uv sync
```

E o comando é o mesmo nos quatro:

```bash
uv run streamlit run src/app.py
```

Os quatro abrem uma interface no browser. O `01` põe os dois prompts lado a
lado, o `02` mostra um diagnóstico e o que ele custou, e o `03` e o `04` são um
chat com o tamanho da janela embaixo de cada resposta.

Cada pasta tem um `README.md` próprio com a explicação completa. Comece por ele.

## Por que Haiku

O `.env.example` aponta para **Haiku**, e isso é escolha pedagógica, não
economia: um modelo com menos reasoning torna o efeito de cada técnica visível
na tela. Num modelo maior o zero-shot já chega perto do chain-of-thought
sozinho, e o contraste que estes exemplos existem para mostrar desaparece.

Trocar é uma linha no `.env` — vale a pena rodar de novo em
`anthropic:claude-sonnet-5` depois, para ver a diferença encolher.

## Como o repositório é organizado

Pastas seguem `nn-slug`: número sequencial + nome do projeto. Cada exemplo é
**autocontido** — `pyproject.toml`, `uv.lock`, `.venv` e `.env` próprios. Não há
workspace nem pacote compartilhado, de propósito: você copia uma pasta sozinha
para outro lugar e ela roda.

Isso significa dependência duplicada entre os exemplos. É intencional, e é um
preço barato perto de poder tratar cada exemplo como um projeto independente.

## Sua chave nunca entra no repositório

Cada exemplo tem `.env.example` com placeholder; o `.env` de verdade está no
`.gitignore`. Nenhum arquivo versionado aqui contém credencial.

## Quer se aprofundar?

Estes exemplos são uma amostra do que é trabalhado nos treinamentos do
**[veronez.io](https://veronez.io/)** — formações em **IA, Cloud e DevOps**.

Se você quer seguir nessa trilha depois da aula, entre em
[veronez.io](https://veronez.io/) e conheça os treinamentos.
