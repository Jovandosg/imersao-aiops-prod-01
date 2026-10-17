# Validação Docker — regras D1–D13

Cada regra tem **comando + resultado esperado**. O relatório final traz uma linha por regra com o resultado **observado** (✅/❌ + valor curto, ex.: "200", "9 registros", "0,2s").

- Não se aplica? → `N/A — motivo` (ex.: "app sem endpoint de métricas"). Nunca omita.
- Falhou? → `docker compose logs app`, diagnostique, corrija, revalide. Só reporte ❌ se não for resolvível sem mudar a app — e diga por quê.

Defina antes: `U=localhost:<porta_app>`, `S=<dir-da-skill>/scripts/smoke-test.sh`.

| # | Regra | Como | Esperado |
|---|---|---|---|
| D1 | Build | `docker compose build` e `docker images <app>:local --format '{{.Size}}'` | imagem criada; reporte o tamanho |
| D2 | Subida ordenada | `docker compose up -d`; `docker compose ps`; `docker compose logs app \| tail` | banco `healthy` antes da app; log de inicialização sem erro de conexão |
| D3 | Liveness | `curl -s $U/health` | 200 + payload (ex.: `{"state":"up",...}`) |
| D4 | Readiness | `curl -s -o /dev/null -w '%{http_code}' $U/ready` | 200 |
| D5 | Carga de dados | seed do repo (ex.: extrair o JSON de um `.http` com `sed -n '/^{/,$p' arquivo.http`) → `curl -X POST ... -d @-` | 2xx. **Use a porta real**, não a do arquivo de exemplo |
| D6 | Leitura | `curl -s $U/ \| grep -c "<texto inserido>"` e `curl -s -o /dev/null -w '%{http_code}' $U/<recurso>/1` | ≥1 ocorrência; 200 |
| D7 | Escrita via form/API | `curl -X POST $U/<rota> --data-urlencode campo=valor ...` | 2xx ou 302 (redirect), conforme a app |
| D8 | Estáticos | `curl -s -o /dev/null -w '%{http_code}' $U/<css-ou-img>` | 200 — prova que WORKDIR e paths relativos estão certos |
| D9 | Métricas | `curl -s $U/metrics \| grep '^<metrica_da_app>'` | métricas presentes |
| D10 | Banco | `docker compose exec -T <db> psql -U <user> -tAc 'select count(*) from "<tabela>";'` | contagem bate com D5+D7 |
| D11 | Fault-injection (se existir) | ex.: `curl -X PUT $U/unreadyfor/5` → poll `/ready` por 1s até 200; `curl -X PUT $U/unhealth` → `/health` → `docker compose restart app` → `/health` | ready 500 por ~N s e volta a 200; health 500 até restart, depois 200 |
| D12 | Persistência | `docker compose down && docker compose up -d` → aguardar `/ready` → repetir D10 | mesma contagem |
| D13 | Shutdown | `time docker compose stop app` | < ~2s. ~10s = PID 1 ignorando SIGTERM → falta tini |

Atalho para D3/D4/D8/D9: `bash $S $U /health /ready /metrics /<css>`.

Para polling sem `sleep` solto: `for i in $(seq 1 15); do [ "$(curl -s -o /dev/null -w '%{http_code}' $U/ready)" = 200 ] && break; command sleep 1; done`.

Ao final, deixe o ambiente de pé (`docker compose up -d` se D13 parou a app).
