# Runbook de observabilidade local

Este diretório provisiona uma stack open source autocontida para o Podman Compose. A API continua sendo a fonte das métricas online; o `process-exporter` lê apenas evidências agregadas e arquivos versionados do pipeline.

## Topologia

```text
FastAPI ── /metrics ───────────────> Prometheus ──> Grafana
   │                                      │
   ├── JSON em runtime/logs ──> Alloy ──> Loki
   │
   └── OTLP/gRPC ──> OTel Collector ──> Tempo

artefatos e relatórios M1–M5 ──> process-exporter ──> Prometheus
jobs prepare/train/evaluate ──> MLflow server + volume ──> MLflow UI
Airflow DAG M1–M4 ──> jobs Python + logs/estado por tarefa ──> Airflow UI
MLflow DB + mlruns versionados ──> seed inicial do volume
Prometheus ── regras ──> Alertmanager
```

## Serviços e persistência

| Serviço | Acesso no host | Persistência |
|---|---|---|
| `api` | `127.0.0.1:8000` | `runtime/serving` e `runtime/logs` |
| `grafana` | `127.0.0.1:3000` | volume `grafana-data` |
| `prometheus` | `127.0.0.1:9090` | volume `prometheus-data`, retenção de sete dias |
| `alertmanager` | `127.0.0.1:9093` | volume `alertmanager-data` |
| `mlflow` | `127.0.0.1:5000` | volume `mlflow-data` |
| `airflow` (profile `orchestration`) | `127.0.0.1:8080` | volume `airflow-data` |
| `prepare`, `train`, `evaluate`, `pipeline` | jobs efêmeros | bind mounts de `data`, `artifacts` e `reports`; volume `mlflow-data` |
| Loki, Tempo, Alloy e Collector | somente rede interna | volumes próprios quando aplicável |
| `process-exporter` | somente rede interna | nenhuma; mounts somente leitura |

A API roda com um worker. Isso é intencional no MVP: o SQLite e o estado demonstrativo da política são locais. Escala horizontal exige substituir esses estados por armazenamento compartilhado antes de aumentar o número de réplicas.

O MLflow não modifica `mlflow.db` do checkout. Na primeira subida, banco e artefatos
versionados são copiados para `mlflow-data`, e as URIs da cópia são adaptadas para os
caminhos internos do container. Os jobs seguintes registram diretamente nesse servidor e
volume, portanto seus novos runs aparecem na UI sem sincronização manual.

## Operação

```powershell
Copy-Item .env.example .env
podman compose config
podman compose up -d --build
podman compose ps
```

Execute todo o processo de dados e ML em um contêiner efêmero:

```powershell
podman compose run --rm --build pipeline
podman compose restart api process-exporter
```

Para rodar etapas isoladas:

```powershell
podman compose run --rm --build prepare
podman compose run --rm --build train
podman compose run --rm --build evaluate
```

O MLflow é iniciado automaticamente como dependência e precisa ficar saudável antes do
job. Acompanhe a execução pelo terminal, por `podman compose logs -f mlflow` e por
`http://127.0.0.1:5000`. Os jobs pertencem ao profile `jobs` e não permanecem ativos após
a conclusão.

### Airflow opcional

Suba a orquestração visual somente quando necessária:

```powershell
podman compose --profile orchestration up -d --build airflow
```

Acesse `http://127.0.0.1:8080` e dispare `datathon_pipeline_m1_m4`. A interface exibe o
grafo `M1 → M2 → M3 → M4`, logs, duração, tentativas e bloqueios por dependência.
O DAG chama os mesmos módulos de `src/`; não existe uma segunda implementação do pipeline.
MLflow permanece responsável pelos experimentos M3/M4.

Para disparar ou parar o componente pela CLI:

```powershell
podman compose --profile orchestration exec airflow `
  airflow dags trigger datathon_pipeline_m1_m4
podman compose --profile orchestration stop airflow
```

O modo standalone usa LocalExecutor e SQLite persistido em `airflow-data`. Ele é adequado
ao ambiente local demonstrativo, não a produção. `AIRFLOW_LOCAL_ALL_ADMINS=true` remove o
login somente porque a porta está vinculada ao loopback; altere para `false` se precisar de
autenticação local.

Os dois dashboards aparecem automaticamente na pasta `Datathon`:

- `Datathon — API e política online`;
- `Datathon — Processo de ML`.

As fontes Prometheus, Loki, Tempo e Alertmanager também são provisionadas automaticamente. Para produzir telemetria de demonstração:

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/recommendations `
  -H "Content-Type: application/json" `
  --data-binary "@examples/recommendation_request.json"
```

Depois de até 15 segundos, a recomendação aparece no Prometheus, o log no Loki e o trace no Tempo.

## Alertas

As regras ficam em `prometheus/rules/datathon.yml` e cobrem:

- API sem scrape ou sem readiness;
- artefato esperado ausente;
- gate técnico ou golden set reprovado;
- recompensa observada abaixo de `0.14109799897383274` após pelo menos 500 feedbacks.

Taxa de erro e latência são recording rules, ainda sem alerta. Os limiares continuam deliberadamente pendentes até existir uma linha de base representativa, conforme `configs/monitoring.yaml`.

O receiver `local-ui` do Alertmanager não envia mensagens externas. Para e-mail ou webhook, adicione o receiver em `alertmanager/alertmanager.yml` usando segredos fora do Git e reinicie somente o serviço:

```powershell
podman compose up -d --force-recreate alertmanager
```

## Diagnóstico

```powershell
podman compose ps
podman compose logs --tail=100 api otel-collector tempo
podman compose logs --tail=100 alloy loki
podman compose logs --tail=100 prometheus alertmanager grafana
```

Consulte a saúde dos targets em `http://127.0.0.1:9090/targets`. Todos os nove jobs devem aparecer como `UP`: `datathon-api`, `datathon-process`, Prometheus, Alertmanager, Grafana, Loki, Tempo, Alloy e Collector.

Para validar novamente os manifests e o código:

```powershell
podman compose config
python -m ruff check .
python -m pytest -q
```

## Encerramento e reset

```powershell
podman compose --profile orchestration down
```

O profile pode ser omitido se o Airflow não estiver ativo. O comando preserva volumes e
os diretórios `runtime/`. Para um reset completo e destrutivo da telemetria local:

```powershell
podman compose --profile orchestration down -v
```

Remova manualmente os arquivos de `runtime/logs` e `runtime/serving` apenas se também quiser apagar logs e decisões locais. Não remova `artifacts/serving/serving.db`, `mlflow.db` ou `mlruns/`: eles são evidências versionadas do projeto.
