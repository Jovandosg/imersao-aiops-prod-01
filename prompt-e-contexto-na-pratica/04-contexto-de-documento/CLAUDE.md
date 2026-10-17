# 04-contexto-de-documento

**A lição:** material que você anexa entra na janela como qualquer outra mensagem — e a saída deixa de adivinhar.

Leia o `CLAUDE.md` da raiz primeiro. As regras da série valem todas aqui.

## O que não fazer neste exemplo

- **Não adicione RAG, embeddings, vector store ou chunking.** O ponto é que o
  documento inteiro entra na janela. Recuperação é outra escala e não está no
  escopo da aula.
- **Não use loader do framework.** O upload devolve bytes e o código faz
  `.decode("utf-8")`; isso se lê sozinho. Um loader esconde exatamente o que a
  aula quer mostrar.
- **Não adicione tools para o modelo ler o arquivo sozinho.** Isso é agente, é a
  aula de loop, e é o Dia 2.
- **O app começa vazio, e continua começando vazio.** Sem documento carregado
  ele é o `03`, e essa é a primeira metade da demonstração: perguntar, ver o
  modelo adivinhar, e só então arrastar o arquivo. Não volte a carregar o
  documento de projeto por padrão para "facilitar" — isso apaga o contraste que
  passou a acontecer na mesma tela.
- **Não troque o `st.file_uploader` por seleção fixa dos arquivos de
  `contexto/`.** É o arrastar que faz o documento parecer um anexo — e é
  justamente essa impressão que o exemplo desmonta ao mostrar o texto virando
  mensagem na lista.
- **Trocar o que está carregado zera a conversa, e tem de continuar zerando.**
  Os documentos moram no começo da lista; remontar a lista é a consequência
  honesta disso. Preservar o histórico exigiria costurar mensagens em volta dos
  documentos — código para esconder a mecânica que a aula ensina.
- **Os documentos ficam em `st.expander`, não viram balão de chat.** Eles estão
  na lista e são enviados como qualquer mensagem, mas renderizados como balão
  ocupam várias telas e empurram o exemplo para fora do projetor. É por isso que
  o render começa depois do prefixo.
- **Não remova o medidor da barra lateral, e não tire o teto de 200k dele.** É
  ele que mostra o preço de cada documento antes mesmo da primeira pergunta.
  `JANELA` é a janela do Haiku 4.5 — se o `MODELO` do `.env` virar outro com
  janela diferente, a constante muda junto.
- **A volta termina em `st.rerun()`, e isso não é enfeite.** A barra lateral é
  desenhada antes do `invoke`; sem o rerun ela fica uma volta atrasada e mostra
  um número que não é o da resposta na tela.
- **Os documentos precisam continuar não-adivinháveis.** Se os fatos virarem
  genéricos, o `03` passa a acertar por sorte e o contraste morre. Números
  específicos, nomes internos, ADRs por número e ações corretivas com dono e
  estado são o que sustentam.
- **Os dois tipos de documento têm trabalhos diferentes, e é isso que faz a
  demonstração.** `projeto-pagamentos-api.md` diz **como o sistema é** — stack,
  como executar, variáveis, a conta de conexões, as ADRs. Os `inc-*.md` dizem
  **o que já deu errado**. Nenhum dos dois responde sozinho "esse banco
  compartilhado é arriscado?": o projeto chama de dívida de roadmap, os
  incidentes mostram dois P1 em três meses. Não misture os papéis — não devolva
  histórico de incidente para o documento de projeto.
- **O INC-2417 é canônico entre os arquivos.** A data (2026-05-19), a causa
  (3 para 5 réplicas em pico) e a ação de prevenção não implementada (alarme de
  `conexões ativas > 85`) são citadas pelo INC-2661, que existe porque essa ação
  ficou em aberto. Mudar um exige reler o outro.
- **A conta de conexões mora no documento de projeto, e só lá.** É o dado que o
  diagnóstico do `02` pede: `max_connections` 100, pool 20 por réplica
  (`DB_MAX_OPEN_CONNS`), 4 réplicas, 15 do `faturamento-worker`, 5 de
  manutenção. Some 100 exatamente. Tirar isso dali quebra o fio entre os dois
  exemplos.
- **Não desalinhe do `02`.** Os documentos respondem a pergunta que o
  diagnóstico do `02` deixa em aberto. Mudar os números aqui exige reler a
  evidência de lá.
- **Não adicione cache, formulário nem streaming ao Streamlit.** O rerun e o
  `st.chat_input` já resolvem, e cada um deles é uma coisa a mais para explicar
  antes de chegar ao ponto da aula.
- **O núcleo tem de continuar reconhecível ao lado do `03`.** `nova_conversa`,
  `mostrar`, o loop de render, o `append` e o `invoke` com a lista inteira são
  os mesmos nos dois — é isso que faz um exemplo explicar o outro. As barras
  laterais divergem (lá ela controla o histórico, aqui ela carrega documento),
  mas o miolo não.
