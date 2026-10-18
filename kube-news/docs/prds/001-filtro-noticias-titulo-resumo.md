---
artifact_type: prd
prd_number: "001"
status: rascunho
priority: média
created: 2026-10-18
depends_on: []
references:
  - docs/trd.md
---

# PRD 001: Filtro de notícias por título e resumo na tela principal

## 1. Contexto

- **Produto/área:** Kube-News — tela principal (listagem de notícias).
- **Estado atual:** a tela principal exibe todas as notícias cadastradas, sem ordenação definida e sem nenhuma forma de busca ou filtro.
- **Problema:** com o aumento da quantidade de notícias, o leitor que procura uma notícia específica precisa percorrer a lista inteira para encontrá-la.

Contexto técnico (stack, ambientes, topologia) em [`docs/trd.md`](../trd.md).

## 2. Solução proposta

### Visão de produto

- A tela principal ganha um campo de busca. Ao buscar, a lista passa a exibir apenas as notícias cujo título ou resumo contém o termo informado.
- A busca é processada no servidor e o resultado é acessível por um link: copiar o endereço da página filtrada e abri-lo de novo reproduz o mesmo resultado.
- Sem termo, a tela principal se comporta exatamente como hoje.

### Decisões de produto

1. **Busca em título e resumo, nunca no conteúdo.** Título e resumo são o que o leitor vê na listagem; buscar no conteúdo traria resultados cujo motivo não aparece na tela.
2. **A busca diferencia acentos.** "noticia" não encontra "Notícia". Decisão consciente, aceitando que quem digita sem acento pode não encontrar.
3. **A busca ignora maiúsculas e minúsculas.** "notícia" encontra "Notícia" e "NOTÍCIA".
4. **Várias palavras exigem todas.** Uma notícia aparece somente se cada palavra do termo estiver presente, em qualquer ordem, no título ou no resumo.
5. **O termo é literal.** Nenhum caractere digitado tem significado especial de curinga.

### Fora do escopo

- **Paginação e ordenação da lista.** Decisão explícita; a lista sem termo continua com todas as notícias e sem ordem definida.
- **Busca no conteúdo da notícia.** Ver decisão 1.
- **Busca que ignora acentos.** Ver decisão 2.
- **Relevância, ranqueamento e destaque do termo no resultado.**
- **Filtros por data, categoria ou autor.** A notícia não possui categoria nem autor.
- **Sugestão ou autocompletar enquanto se digita.**

## 3. Funcionalidades

### US01: Buscar notícias por termo

Como leitor do Kube-News, quero buscar notícias por um termo no título ou no resumo, para encontrar rapidamente a notícia que procuro sem percorrer a lista inteira.

**Rules:**
- A lista exibe somente notícias em que todas as palavras do termo aparecem no título ou no resumo (cada palavra pode estar em um ou no outro).
- A correspondência considera trechos de palavra: "kube" encontra "Kubernetes".
- Acentos são diferenciados; maiúsculas e minúsculas não.
- O conteúdo da notícia não é considerado.
- Cada notícia aparece no máximo uma vez no resultado, mesmo que o termo apareça no título e no resumo.

**Edge cases:**
- Termo vazio ou formado só por espaços → a tela exibe todas as notícias, como hoje.
- Espaços no início, no fim ou repetidos entre palavras → são ignorados.
- Termo com caracteres como `%`, `_` ou aspas → tratados como texto comum.
- Termo sem acento procurando palavra acentuada ("noticia") → não encontra "Notícia"; comportamento esperado, não erro.

### US02: Entender e ajustar o resultado da busca

Como leitor, quero ver qual termo está aplicado e ser avisado quando nada for encontrado, para saber se refino a busca ou volto à lista completa.

**Rules:**
- Após a busca, o campo continua preenchido com o termo aplicado.
- Existe uma forma visível de limpar a busca e voltar à lista completa.
- Quando nenhuma notícia corresponde, a tela exibe uma mensagem própria de "nenhuma notícia encontrada para [termo]", diferente da mensagem de "ainda não temos nenhum post".

**Edge cases:**
- Busca sem resultado em base sem nenhuma notícia → prevalece a mensagem de base vazia, já existente.
- Termo muito longo → a busca é feita normalmente e simplesmente não encontra resultados; nenhum erro é exibido.

### US03: Compartilhar uma busca por link

Como leitor, quero que o endereço da página reflita a busca feita, para poder recarregar, voltar no navegador ou enviar o link a outra pessoa com o mesmo resultado.

**Rules:**
- Abrir o link de uma busca reproduz o mesmo filtro, independentemente de qual instância da aplicação atende a requisição.
- Voltar no navegador retorna à busca (ou à lista) anterior.

**Edge cases:**
- Link de busca aberto depois que novas notícias foram cadastradas → o resultado inclui as novas notícias que correspondem ao termo.

## 5. Critérios de aceite

### 5a. Critérios da feature

- [ ] **AC01 — Busca encontra por título**
  - **Razão de negócio:** objetivo central da feature.
  - **Como verificar:** com uma notícia de título "Kubernetes na prática", buscar "prática" exibe essa notícia.
- [ ] **AC02 — Busca encontra por resumo**
  - **Razão de negócio:** o resumo é a segunda informação visível na listagem.
  - **Como verificar:** buscar uma palavra presente só no resumo exibe a notícia.
- [ ] **AC03 — Conteúdo não é considerado**
  - **Razão de negócio:** decisão de produto 1.
  - **Como verificar:** buscar uma palavra presente só no conteúdo não exibe a notícia.
- [ ] **AC04 — Acentos são diferenciados**
  - **Razão de negócio:** decisão de produto 2.
  - **Como verificar:** com uma notícia de título "Notícia do cluster", buscar "noticia" não a exibe; buscar "notícia" a exibe.
- [ ] **AC05 — Maiúsculas e minúsculas são ignoradas**
  - **Razão de negócio:** decisão de produto 3.
  - **Como verificar:** buscar "KUBERNETES" e "kubernetes" retorna o mesmo resultado.
- [ ] **AC06 — Várias palavras exigem todas**
  - **Razão de negócio:** decisão de produto 4.
  - **Como verificar:** "deploy cluster" exibe uma notícia com "deploy" no título e "cluster" no resumo; não exibe uma notícia que só contém "deploy".
- [ ] **AC07 — Termo é literal**
  - **Razão de negócio:** decisão de produto 5.
  - **Como verificar:** buscar "%" ou "_" não retorna todas as notícias; só retorna notícias que contêm literalmente o caractere.
- [ ] **AC08 — Termo vazio mantém comportamento atual**
  - **Razão de negócio:** não regredir a tela principal.
  - **Como verificar:** buscar vazio ou só espaços exibe todas as notícias.
- [ ] **AC09 — Mensagem de busca sem resultado**
  - **Razão de negócio:** o leitor precisa distinguir "nada encontrado" de "base vazia".
  - **Como verificar:** com notícias cadastradas, buscar um termo inexistente exibe a mensagem de nenhum resultado com o termo, e não a de base vazia.
- [ ] **AC10 — Termo permanece no campo**
  - **Razão de negócio:** permitir refinar a busca.
  - **Como verificar:** após buscar, o campo exibe o termo aplicado.
- [ ] **AC11 — Busca acessível por link**
  - **Razão de negócio:** compartilhar e recarregar o resultado.
  - **Como verificar:** copiar o endereço de uma busca, abrir em nova aba (ou recarregar repetidas vezes, sendo atendido por instâncias diferentes) e obter o mesmo resultado.
- [ ] **AC12 — Tempo de resposta da busca**
  - **Razão de negócio:** a busca não pode deixar a tela principal perceptivelmente mais lenta que hoje.
  - **Como verificar:** com 1.000 notícias cadastradas, a página com busca responde em até 1 segundo no ambiente cloud.

### 5b. Métricas de sucesso

| Métrica | Baseline (fonte) | Meta | Prazo | Mín. aceitável | Responsável |
|---|---|---|---|---|---|
| Critérios AC01–AC12 aprovados | 0/12 | 12/12 | Entrega da feature | 12/12 | Fabricio Veronez |

Projeto didático, sem usuários reais para medir adoção; o sucesso é medido pelos critérios de aceite.

## 6. Riscos e dependências

| Risco | Impacto | Mitigação | Status |
|---|---|---|---|
| Leitor busca sem acento e não encontra notícia acentuada | Médio | Decisão consciente; revisar se houver reclamação | Monitorando |
| Palavra presente só no conteúdo não é encontrada (título + resumo somam no máximo 80 caracteres) | Médio | Decisão consciente; busca no conteúdo pode virar novo PRD | Monitorando |
| Sem paginação, a lista sem termo continua extensa | Médio | Fora do escopo por decisão; pode virar novo PRD | Monitorando |
| Volume crescer muito além de milhares de notícias e a busca ficar lenta | Baixo | AC12 sinaliza a degradação | Pendente |

**Dependências:** nenhuma.

## 7. Referências

- [`docs/trd.md`](../trd.md) — stack, ambientes e topologia do Kube-News.

## 8. Registro de decisões

- **2026-10-18:** Busca processada no servidor. Motivo: decisão do usuário; o resultado fica acessível por link e independe de qual instância atende.
- **2026-10-18:** Busca restrita a título e resumo. Motivo: decisão do usuário; são as informações visíveis na listagem.
- **2026-10-18:** Busca diferencia acentos. Motivo: decisão do usuário. Ignorar acentos foi descartado, o que também evita qualquer dependência nova no banco.
- **2026-10-18:** Paginação e ordenação fora do escopo. Motivo: decisão do usuário.
- **2026-10-18:** Premissas do draft aprovadas pelo usuário (maiúsculas/minúsculas ignoradas, todas as palavras exigidas, termo literal, limiar de AC12, prioridade média). Motivo: revisão do draft.
- **2026-10-18:** Sem `depends_on`. Motivo: não há outros PRDs no projeto.
