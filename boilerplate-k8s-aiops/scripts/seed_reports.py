"""Insere relatorios em todos os seis status para validar a interface sem o agente.

Uso: `uv run python scripts/seed_reports.py` (banco migrado; usa DATABASE_URL do .env).
"""

import asyncio
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.database import get_database_url
from my_agent_app.models.report import Report, ReportStatus

NGINX_MARKDOWN = """\
# Imagem inexistente no deployment nginx

- **Severidade:** CRITICO
- **Namespace:** teste-a
- **Recursos Afetados:** deployment/nginx
- **Conclusao:** conclusiva

### Causa Raiz
O deployment `nginx` usa a imagem `ngin:latest`, que nao existe no registry.

### Evidencias
- Evento `Failed`: Failed to pull image "ngin:latest"
- Saida do kubectl:

```
NAME                     READY   STATUS             RESTARTS   AGE   NOMINATED NODE <none>
nginx-7d9c6b8f5d-abcde   0/1     ImagePullBackOff   0          5m    <none>
```

| Recurso | Status |
|---------|--------|
| nginx-7d9c6b8f5d-abcde | ImagePullBackOff |

### Solucao Recomendada
Corrigir a imagem para `nginx:latest`.

### Comando Sugerido
kubectl patch deployment nginx -n teste-a --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx","image":"nginx:latest"}]}}}}'
"""

KUBENEWS_MARKDOWN = """\
# Senha do banco divergente no kube-news

- **Severidade:** ALTO
- **Namespace:** teste-b
- **Recursos Afetados:** deployment/kubenews

### Causa Raiz
`DB_PASSWORD` (`pg123`) diverge de `POSTGRES_PASSWORD` (`pg1234`).
"""

CORRECTION_OK = """\
CORRIGIDO: imagem ajustada para nginx:latest

## Acoes Executadas

### Problema 1: Imagem inexistente no deployment nginx
- **Status:** Corrigido
- **Acao:** kubectl_patch strategic na imagem
- **Validacao:** 1/1 pods Running e Ready
"""

CORRECTION_FAIL = """\
FALHA: pods continuam em CrashLoopBackOff

## Acoes Executadas

### Problema 1: Senha do banco divergente no kube-news
- **Status:** Falha
- **Acao:** kubectl_patch strategic em DB_PASSWORD
- **Validacao:** pods reiniciando
"""


def seed_reports(now: datetime) -> list[Report]:
    def ago(minutes: int) -> datetime:
        return now - timedelta(minutes=minutes)

    return [
        Report(status=ReportStatus.EM_ANALISE, event_uids=["seed-em-analise"], created_at=ago(1)),
        Report(status=ReportStatus.INCOMPLETO, event_uids=["seed-incompleto"], created_at=ago(10)),
        Report(
            status=ReportStatus.COMPLETO, event_uids=["seed-nginx-1", "seed-nginx-2"], created_at=ago(20),
            title="Imagem inexistente no deployment nginx", severity="CRITICO", namespace="teste-a",
            markdown=NGINX_MARKDOWN,
        ),
        Report(
            status=ReportStatus.CORRIGINDO, event_uids=["seed-corrigindo"], created_at=ago(30),
            title="Correcao em andamento", severity="MEDIO", namespace="teste-c",
            markdown="# Correcao em andamento\n\nRelatorio em correcao.", correction_started_at=ago(2),
        ),
        Report(
            status=ReportStatus.CORRIGIDO, event_uids=["seed-corrigido"], created_at=ago(40),
            title="Imagem inexistente (corrigido)", severity="CRITICO", namespace="teste-a",
            markdown=NGINX_MARKDOWN, correction_result=CORRECTION_OK, corrected_at=ago(35),
            correction_started_at=ago(38),
        ),
        Report(
            status=ReportStatus.FALHA_CORRECAO, event_uids=["seed-kubenews"], created_at=ago(50),
            title="Senha do banco divergente no kube-news", severity="ALTO", namespace="teste-b",
            markdown=KUBENEWS_MARKDOWN, correction_result=CORRECTION_FAIL, correction_started_at=ago(48),
        ),
    ]


async def main() -> None:
    load_dotenv()
    engine = create_async_engine(get_database_url())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            reports = seed_reports(datetime.now(UTC))
            session.add_all(reports)
        for report in reports:
            print(f"{report.status:<15} {report.id}  {report.title or '(sem titulo)'}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
