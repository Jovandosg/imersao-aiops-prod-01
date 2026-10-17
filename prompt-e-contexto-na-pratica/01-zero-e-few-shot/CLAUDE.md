# 01-zero-e-few-shot

**A lição:** o que dois exemplos no prompt mudam — e o que eles custam.

Leia o `CLAUDE.md` da raiz primeiro. As regras da série valem todas aqui.

Os quatro exemplos têm interface (Streamlit). O que é próprio daqui são as
**duas colunas**: a lição é uma comparação lado a lado, e lado a lado precisa de
dois painéis na mesma tela.

## O que não fazer neste exemplo

- **Não descreva o formato do post-mortem no `SYSTEM_PROMPT`.** Ele tem duas
  linhas e diz só quem o modelo é. Se o prompt ensinar as seções, os exemplos
  ficam sem função, os dois painéis saem parecidos e a comparação vira teatro.
  É o modo de falha número um daqui.
- **Não esconda o prompt da tela, e não monte o que a tela mostra separado do
  que o `invoke` recebe.** A função `mensagens()` é fonte única para os dois. O
  aluno precisa ver o que vai ser executado de verdade — se um dia a tela
  mostrar uma versão "formatada para exibição", o exemplo passa a mentir.
- **Não rotule as mensagens na tela.** Nada de `SystemMessage`/`HumanMessage`
  aparecendo para a turma: o array de mensagens é a lição do `03`, e aqui ela
  ainda não aconteceu. Na tela existe "o prompt", e só.
- **Não remova nenhum dos dois painéis.** O da direita sozinho parece correto —
  é justamente por isso que o da esquerda precisa estar do lado. Sem o
  contrafactual não há lição.
- **Não use os exemplos como alvo.** Exemplo que é o gabarito não mede
  generalização, mede memória. O `INCIDENTE` tem que ser um caso que os
  exemplos não cobrem.
- **Não deixe o `INCIDENTE` estruturado.** Ele é anotação crua de plantão, fora
  de ordem e sem seção nenhuma, de propósito. Se ele já vier no formato, o
  painel da esquerda copia e o contraste desaparece.
- **Não suba para 4 ou mais exemplos.** Post-mortem é saída longa; o terceiro
  exemplo incha a entrada sem ensinar nada novo, e o readout é onde esse custo
  aparece.
- **Não troque os exemplos por três da mesma causa.** Certificado, disco e
  configuração-como-código são causas distintas de propósito — exemplos
  homogêneos ensinam o assunto em vez do formato.
- **Não reaproveite o incidente de esgotamento de pool do `02`.** É o incidente
  daquele exemplo, e os dois não podem convergir.
- **Não remova o readout de custo, e não o mande para o rodapé.** São os mesmos
  três números do `02` (entrada, saída, tempo), mas em `st.metric` no topo de
  cada coluna. No rodapé eles cairiam em alturas diferentes, porque as respostas
  têm tamanhos diferentes — e um readout que não dá para comparar não serve para
  nada. É a **entrada** crescendo que importa aqui: o oposto do `02`, onde
  cresce a saída.
- **Não adicione `session_state`, cache ou formulário ao Streamlit.** O rerun do
  botão já resolve. Estado é uma coisa a mais para explicar antes de chegar ao
  ponto da aula. (O `03` e o `04` usam `session_state` porque lá a lista da
  conversa *é* a lição; aqui não há lista, há duas chamadas independentes.)
