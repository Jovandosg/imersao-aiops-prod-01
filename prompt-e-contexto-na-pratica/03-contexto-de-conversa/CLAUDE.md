# 03-contexto-de-conversa

**A lição:** o histórico é um array que o *seu* código reenvia — o modelo não lembra.

Leia o `CLAUDE.md` da raiz primeiro. As regras da série valem todas aqui.

## O que não fazer neste exemplo

- **Não use abstração de memória do framework.** A lista explícita é a lição.
  Qualquer coisa que esconda o `append` e o reenvio destrói o exemplo.
- **A lista vive em `st.session_state`, e vive exposta.** O `append` e o
  `invoke` recebendo a lista inteira precisam continuar visíveis no código, em
  linhas que dá para ler no projetor.
- **Não persista a conversa em disco nem adicione múltiplas sessões.** Os três
  limites (morre ao fechar · uma conversa só · cresce sem freio) são conteúdo
  falado, não defeitos a corrigir.
- **Não adicione poda, resumo ou janela deslizante.** A janela crescendo sem
  freio é o que a aula mostra.
- **Não remova o botão `limpar`** (era um comando digitado quando isto era um
  app de terminal) — é a prova ao vivo do esquecimento.
- **Não remova o contador de janela.** É ele que separa este exemplo de uma aula
  de "memória" e o torna uma aula de **contexto**.
- **Não remova o medidor da barra lateral, e não tire o teto de 200k dele.** O
  contador embaixo de cada resposta dá o número; é o teto que o transforma em
  conta. `JANELA` é a janela do Haiku 4.5 — se um dia o `MODELO` do `.env` virar
  outro com janela diferente, a constante muda junto.
- **Não remova o checkbox `acumular o histórico`.** Desmarcado, a lista é zerada
  antes de cada pergunta e o medidor para de subir: é a lição inteira num
  clique, e é mais rápido na tela do que a sequência do `limpar`. O `limpar`
  continua — um apaga o passado, o outro desliga o futuro.
- **A volta termina em `st.rerun()`, e isso não é enfeite.** A barra lateral é
  desenhada antes do `invoke`; sem o rerun ela fica uma volta atrasada e mostra
  um número que não é o da resposta na tela.
- **Não adicione cache, formulário nem streaming ao Streamlit.** O rerun e o
  `st.chat_input` já resolvem, e cada um deles é uma coisa a mais para explicar
  antes de chegar ao ponto da aula.
- **O núcleo tem de continuar reconhecível ao lado do `04`.** `nova_conversa`,
  `mostrar`, o loop de render, o `append` e o `invoke` com a lista inteira são
  os mesmos nos dois, e é isso que faz um exemplo explicar o outro. As barras
  laterais divergem de propósito — aqui ela desliga o histórico, lá ela carrega
  documento —, mas o miolo não. Antes de mexer no miolo de um, verifique o
  efeito no par.
