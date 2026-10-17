"""A evidencia do incidente.

Fica separada do `app.py` por um motivo pratico: e um bloco longo, e com ela la
as tres linhas que interessam na aula estariam soterradas.

O desenho dela e o conteudo do exemplo, entao mexer aqui muda o que a aula
demonstra. Tres propriedades sustentam o chain-of-thought:

1. HA MAIS DE UMA HIPOTESE PLAUSIVEL. Memoria, CPU e banco competem. Se a
   evidencia entregar a causa de bandeja, zero-shot acerta e o exemplo perde a
   razao de existir.
2. HA O QUE DESCARTAR. Memoria e CPU estao estaveis de proposito — sao os
   ramos que o raciocinio explicito precisa podar para chegar ao banco.
3. O DADO QUE FECHA O DIAGNOSTICO NAO ESTA AQUI. O limite de conexoes do banco
   compartilhado esta de fora, e isso e deliberado: e o que o exemplo `04`
   entrega, via documento em contexto. A boa resposta daqui termina dizendo o
   que falta checar — e o `04` e quem checa.
"""

EVIDENCIA = """
INCIDENTE — pagamentos-api, aberto 03:14, em andamento

Log da aplicação (pagamentos-api, últimos 20 min, amostra):
  03:12:41 WARN  timeout acquiring connection from pool (waited 30s)
  03:12:41 ERROR POST /v1/cobrancas -> 503
  03:13:02 WARN  timeout acquiring connection from pool (waited 30s)
  03:13:55 INFO  POST /v1/cobrancas -> 201 (1.4s)
  03:14:07 ERROR POST /v1/cobrancas -> 503
  03:14:09 WARN  timeout acquiring connection from pool (waited 30s)
  (o erro é intermitente: parte das requisições ainda passa)

Métricas (janela de 3h, pagamentos-api):
  latência p99            220ms -> 4.8s
  taxa de erro 5xx        0.1%  -> 12%
  memória do container    estável em 380Mi de 1Gi
  CPU do container        estável em 22% do limite
  réplicas em execução    4, nenhuma reiniciada

Métricas (mesma janela, db-financeiro / PostgreSQL):
  conexões ativas         38 -> 100, e cravado em 100 há 40 min
  CPU do banco            estável em 31%
  queries lentas (>1s)    sem variação relevante

Mudanças na janela:
  01:05  deploy pagamentos-api v2.14.0
         changelog: "conciliação de cobranças passa a rodar em paralelo
         (workers de 4 para 12) para reduzir a fila noturna"
  sem mudança de infraestrutura
  sem alteração de configuração no db-financeiro

Outros serviços:
  faturamento-worker também começou a registrar erro de conexão às 03:09.
  Ele NÃO teve deploy nesta janela e não foi alterado há 11 dias.
"""
