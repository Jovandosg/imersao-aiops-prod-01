# 02-chain-of-thought

**A lição:** raciocínio explícito como recurso — e como custo.

Leia o `CLAUDE.md` da raiz primeiro. As regras da série valem todas aqui.

## O que não fazer neste exemplo

- **Não simplifique a evidência em `src/evidencia.py`.** O docstring do arquivo
  explica as três propriedades que a sustentam. Tirar os sinais estáveis
  (memória, CPU) elimina o que há para descartar, e a técnica deixa de ter o que
  demonstrar.
- **Não acrescente o limite de conexões do banco à evidência.** A ausência dele
  é o gancho para o `04`, que entrega esse dado por documento em contexto.
- **Não adicione tools nem loop.** ReAct é conceito na aula de prompt e só é
  aberto na aula de loop. Este exemplo raciocina, não age.
- **Não transforme em comparação A/B com o `01`, e não adicione um segundo
  painel.** O A/B mora dentro do `01`, entre zero-shot e few-shot na mesma
  tarefa. Entre os dois exemplos a comparação é par a par, pelo readout: aqui
  cresce a saída, lá cresce a entrada. Cada exemplo roda na tarefa em que a sua
  técnica encaixa.
- **Não remova o readout de custo, não o mande para o rodapé e não troque as
  métricas** — é metade do ponto do exemplo. São os mesmos três números do `01`
  (entrada, saída, tempo), em `st.metric` acima da resposta. Aqui é a **saída**
  crescendo que importa.
- **Não adicione `session_state`, cache ou formulário ao Streamlit.** O rerun do
  botão já resolve.
