# 04 — O documento em contexto

O mesmo chat do [`03`](../03-contexto-de-conversa), com uma diferença: aqui você
carrega documentos e eles entram na conversa antes da primeira pergunta.

**O app começa vazio**, e isso é o desenho. Sem documento carregado ele é o `03`
— mesma lista, mesmo comportamento, mesma adivinhação. O contraste acontece na
mesma tela, ao vivo, quando o arquivo entra.

## Como rodar

```bash
cp .env.example .env      # preencha ANTHROPIC_API_KEY
uv sync
uv run streamlit run src/app.py
```

Na barra lateral você arrasta os arquivos. Eles estão em `contexto/`, mas
qualquer `.md` ou `.txt` da sua máquina serve.

## Os documentos, e o trabalho de cada um

| Arquivo | O que ele é |
|---|---|
| `projeto-pagamentos-api.md` | **como o sistema é** — stack, como executar, variáveis de ambiente, dependências, a conta de conexões do banco, rollback, ADRs |
| `inc-2417-*.md` · `inc-2508-*.md` · `inc-2661-*.md` | **o que já deu errado** — três post-mortems do mesmo serviço |

A separação é o exemplo. Documento de projeto descreve o desenho; post-mortem
descreve a realidade. Perguntas diferentes precisam de arquivos diferentes na
janela, e algumas precisam dos dois.

## A demonstração, na ordem

1. **Sem carregar nada**, pergunte:
   > Qual é o limite de conexões do banco do pagamentos-api?

   Ele não tem como saber. Vai adivinhar um número plausível, ou dizer que
   depende — as duas saídas são igualmente inúteis para quem está de plantão.

2. **Arraste `contexto/projeto-pagamentos-api.md`** para a barra lateral e
   repita a pergunta. Agora ele responde `max_connections = 100`, pool de 20 por
   réplica (`DB_MAX_OPEN_CONNS`), 4 réplicas, e diz de onde tirou. A saída
   deixou de adivinhar porque o documento já dizia.

3. **Ainda só com o documento de projeto**, pergunte:
   > O banco compartilhado é um risco real?

   Ele vai responder o que o documento diz: dívida conhecida, ADR-0031,
   separação no roadmap sem data. Está correto — e passa a impressão de que é um
   problema teórico.

4. **Arraste os três incidentes junto** e repita. Agora não é teórico: dois P1
   em três meses, e a ação de prevenção do primeiro segue aberta. Pergunte
   também algo que só existe cruzando os arquivos:
   > Quantas vezes já estouramos o teto de conexões, e por que aconteceu de novo?

   A resposta precisa do INC-2417 *e* do INC-2661 — o segundo aconteceu porque o
   alarme registrado no primeiro nunca foi implementado.

Vale perguntar também o que os documentos **não** cobrem — ajuste de
`max_connections`, por exemplo. O prompt pede que ele diga que não cobre em vez
de completar com o que costuma ser verdade em outros lugares.

## Trocar o que está carregado refaz a conversa

Os documentos moram no **começo** da lista. Não há como trocar um sem remontar a
lista inteira, então marcar ou remover um arquivo zera o histórico. Isso não é
limitação: é o que torna visível que documento não é "anexo" — é posição na
janela.

## Escolher o que entra é a engenharia

O passo 3 é o ponto da aula. Com só o documento de projeto na janela, a resposta
sobre o banco compartilhado é **correta e incompleta** — e nada na tela avisa
que está incompleta. Não dá erro, não dá aviso: dá um parágrafo confiante.

O modelo só sabe o que está na janela. Decidir o que colocar lá é trabalho de
quem monta o contexto, e é a diferença entre uma resposta certa e uma resposta
útil.

## Os documentos fecham o exemplo `02`

Todos são do mesmo serviço do incidente de
[`02-chain-of-thought`](../02-chain-of-thought). Lá o diagnóstico terminava
dizendo o que faltava checar: o limite de conexões do banco compartilhado. É
este material que responde.

Cole a evidência do `02` aqui com o documento de projeto e os incidentes
carregados e peça o diagnóstico — a resposta muda de "provavelmente exaustão de
conexões, confirme o limite" para a conta fechada, com o histórico junto. É o
que a engenharia de contexto compra.

## O que os documentos têm, e por quê

Fatos **não-adivinháveis**: números de pool e de réplica, o nome exato da
variável que define o pool, uma dependência compartilhada, um procedimento de
rollback com regra de aprovação, uma janela de manutenção, ADRs citadas por
número e ações corretivas com dono e estado. Nada disso é dedutível do nome do
serviço — e é por isso que a diferença entre o `03` e o `04` é visível.

## Encher a janela tem preço

O contador continua embaixo de cada resposta, e a barra lateral põe o mesmo
número contra o teto de **200 mil tokens**. Carregue um arquivo de cada vez e
veja o medidor subir antes mesmo da primeira pergunta — você paga por aquele
texto em toda chamada seguinte. Documento que não decide nada é custo sem
retorno.

## Arquivos

```
src/app.py                                    o chat, o upload e a injeção na conversa
contexto/projeto-pagamentos-api.md            o projeto: stack, como executar e a conta de conexões
contexto/inc-2417-esgotamento-de-conexoes.md  o primeiro esgotamento de conexões
contexto/inc-2508-antifraude-falha-aberta.md  uma falha que não derrubou nada
contexto/inc-2661-pool-do-faturamento-worker.md   o mesmo estouro, pelo outro lado do banco
.env.example                                  a chave da API e o modelo
pyproject.toml                                as dependências
```
