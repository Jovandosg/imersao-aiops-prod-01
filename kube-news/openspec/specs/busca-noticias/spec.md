# busca-noticias Specification

## Purpose
TBD - Busca de notícias por termo no título e no resumo.

## Requirements

### Requirement: Busca por termo no título e no resumo
A rota `GET /` SHALL aceitar o parâmetro de query `q`. Com um termo válido, a lista MUST exibir somente as notícias em que cada palavra do termo aparece, como trecho, no título ou no resumo. Cada palavra pode estar em um campo ou no outro. O conteúdo da notícia MUST NOT ser considerado. Cada notícia MUST aparecer no máximo uma vez no resultado.

#### Scenario: Encontra por título
- **WHEN** existe uma notícia de título "Kubernetes na prática" e o leitor acessa `/?q=prática`
- **THEN** a notícia aparece na lista

#### Scenario: Encontra por resumo
- **WHEN** uma palavra está só no resumo de uma notícia e o leitor busca essa palavra
- **THEN** a notícia aparece na lista

#### Scenario: Trecho de palavra
- **WHEN** existe uma notícia de título "Kubernetes na prática" e o leitor busca "kube"
- **THEN** a notícia aparece na lista

#### Scenario: Conteúdo é ignorado
- **WHEN** uma palavra está só no conteúdo de uma notícia e o leitor busca essa palavra
- **THEN** a notícia não aparece na lista

#### Scenario: Termo aparece no título e no resumo
- **WHEN** o termo buscado está no título e no resumo da mesma notícia
- **THEN** a notícia aparece uma única vez

### Requirement: Várias palavras exigem todas
Um termo com várias palavras SHALL encontrar só as notícias que contêm todas elas, em qualquer ordem, cada uma no título ou no resumo.

#### Scenario: Palavras distribuídas entre título e resumo
- **WHEN** uma notícia tem "deploy" no título e "cluster" no resumo e o leitor busca "deploy cluster"
- **THEN** a notícia aparece na lista

#### Scenario: Falta uma das palavras
- **WHEN** uma notícia contém "deploy" mas não contém "cluster" no título nem no resumo, e o leitor busca "deploy cluster"
- **THEN** a notícia não aparece na lista

#### Scenario: Ordem das palavras é indiferente
- **WHEN** o leitor busca "cluster deploy" em vez de "deploy cluster"
- **THEN** o resultado é o mesmo

### Requirement: Maiúsculas ignoradas, acentos diferenciados
A correspondência SHALL ignorar maiúsculas e minúsculas, inclusive em letras acentuadas, e MUST diferenciar letras acentuadas das não acentuadas.

#### Scenario: Caixa ignorada
- **WHEN** o leitor busca "KUBERNETES" e depois "kubernetes"
- **THEN** os dois resultados são iguais

#### Scenario: Caixa ignorada em letra acentuada
- **WHEN** existe uma notícia de título "Notícia do cluster" e o leitor busca "NOTÍCIA"
- **THEN** a notícia aparece na lista

#### Scenario: Acento diferenciado
- **WHEN** existe uma notícia de título "Notícia do cluster" e o leitor busca "noticia"
- **THEN** a notícia não aparece na lista

### Requirement: Termo literal
Nenhum caractere do termo SHALL ter significado especial. Os caracteres `%`, `_`, `\` e aspas MUST ser tratados como texto comum.

#### Scenario: Percentual não é curinga
- **WHEN** o leitor busca "%" e só uma das notícias contém o caractere "%" no título ou no resumo
- **THEN** só essa notícia aparece na lista

#### Scenario: Sublinhado não é curinga
- **WHEN** o leitor busca "_" e nenhuma notícia contém "_" no título ou no resumo
- **THEN** a tela exibe a mensagem de nenhum resultado

#### Scenario: Aspas e barra invertida
- **WHEN** o leitor busca um termo com aspas simples, aspas duplas ou barra invertida
- **THEN** a página responde normalmente, sem erro, e só aparecem notícias que contêm esses caracteres literalmente

### Requirement: Normalização do termo
O termo SHALL ter os espaços do início e do fim removidos, e espaços repetidos entre palavras MUST ser tratados como um só separador. Um termo vazio, só com espaços, ou um `q` que não seja uma string única (por exemplo `?q=a&q=b` ou `?q[x]=y`) MUST ser tratado como ausência de termo.

#### Scenario: Termo vazio
- **WHEN** o leitor acessa `/?q=` ou `/?q=%20%20%20`
- **THEN** a tela exibe todas as notícias, como sem busca

#### Scenario: Espaços extras
- **WHEN** o leitor busca "  deploy    cluster  "
- **THEN** o resultado é igual ao da busca "deploy cluster"

#### Scenario: Parâmetro malformado
- **WHEN** o leitor acessa `/?q=a&q=b` ou `/?q[x]=y`
- **THEN** a página responde normalmente, sem erro, e exibe todas as notícias

#### Scenario: Termo muito longo
- **WHEN** o leitor busca um termo de centenas de caracteres que nenhuma notícia contém
- **THEN** a tela exibe a mensagem de nenhum resultado, sem erro

### Requirement: Formulário de busca acima da lista
Quando existe pelo menos uma notícia cadastrada, a tela principal SHALL exibir, acima da lista, um formulário de busca que envia o termo por `GET` para `/` no parâmetro `q`. Após a busca, o campo MUST continuar preenchido com o termo aplicado (já normalizado). Quando há termo aplicado, a tela MUST exibir um link "Limpar" que leva a `/`. O termo MUST ser escapado ao ser exibido na página.

#### Scenario: Campo preenchido
- **WHEN** o leitor busca "deploy"
- **THEN** o campo de busca exibe "deploy"

#### Scenario: Limpar a busca
- **WHEN** há um termo aplicado e o leitor clica em "Limpar"
- **THEN** a tela volta a exibir todas as notícias, com o campo vazio

#### Scenario: Sem termo não há link de limpar
- **WHEN** o leitor acessa `/` sem termo
- **THEN** o formulário aparece e o link "Limpar" não aparece

#### Scenario: Termo com HTML
- **WHEN** o leitor busca `<script>alert(1)</script>`
- **THEN** o termo aparece como texto no campo e na mensagem, sem ser interpretado como HTML

### Requirement: Mensagem de busca sem resultado
Quando há notícias cadastradas e nenhuma corresponde ao termo, a tela SHALL exibir a mensagem "Nenhuma notícia encontrada para "[termo]"", diferente da mensagem de base vazia, mantendo o formulário visível. Quando não há nenhuma notícia cadastrada, a tela MUST exibir a mensagem de base vazia já existente, sem formulário de busca, com ou sem `q` na URL.

#### Scenario: Nenhum resultado com base preenchida
- **WHEN** existem notícias e o leitor busca um termo que nenhuma contém
- **THEN** a tela exibe "Nenhuma notícia encontrada para" seguido do termo, o formulário continua visível, e a mensagem de base vazia não aparece

#### Scenario: Base vazia com termo
- **WHEN** não existe nenhuma notícia e o leitor acessa `/?q=deploy`
- **THEN** a tela exibe a mensagem "Ainda não temos nenhum post" e não exibe o formulário de busca

#### Scenario: Base vazia sem termo
- **WHEN** não existe nenhuma notícia e o leitor acessa `/`
- **THEN** a tela é igual à de hoje

### Requirement: Resultado acessível por link
O resultado da busca SHALL depender só do parâmetro `q` da URL e do estado do banco, sem estado em memória na aplicação, de modo que abrir o mesmo endereço reproduza o mesmo filtro em qualquer instância.

#### Scenario: Recarregar ou abrir em outra aba
- **WHEN** o leitor copia o endereço de uma busca e o abre de novo, sendo atendido por qualquer instância
- **THEN** o resultado é o mesmo

#### Scenario: Notícias novas entram no resultado
- **WHEN** uma notícia que corresponde ao termo é cadastrada depois e o leitor abre de novo o link da busca
- **THEN** a notícia nova aparece no resultado

#### Scenario: Voltar no navegador
- **WHEN** o leitor faz uma busca e depois outra, e usa o voltar do navegador
- **THEN** a tela exibe a busca anterior

### Requirement: Tempo de resposta
Com 1.000 notícias cadastradas, a página com busca SHALL responder em até 1 segundo no ambiente cloud.

#### Scenario: Carga de 1.000 notícias
- **WHEN** a base tem 1.000 notícias e o leitor faz uma busca no ambiente cloud
- **THEN** a resposta chega em até 1 segundo
