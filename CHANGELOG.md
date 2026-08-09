# Changelog

As mudanças relevantes deste projeto são documentadas neste arquivo. O formato segue os
princípios do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), sem criar uma
versão final enquanto os gates de revisão humana, vídeo e release permanecerem abertos.

## [Não publicado] — 2026-08-09

### Dados e modelagem

- Pipeline reproduzível M1–M4 para tradução PT-BR, validação contratual, deduplicação,
  preparação dos splits, treino e avaliação de política.
- Bloqueio de `duration`, campanha bruta, identificadores e demais campos indisponíveis
  antes da decisão, evitando vazamento temporal.
- Preprocessing ajustado exclusivamente no treino, com splits estratificados e hashes de
  linhagem versionados.
- Baselines determinístico, Dummy e Regressão Logística, com PR-AUC, ROC-AUC, Brier,
  calibração, matriz de confusão e métricas por fatia.
- Thompson Sampling Beta-Bernoulli segmentado, fallback global, atualização idempotente,
  estado persistido e replay factual com 30 seeds e bootstrap de 95%.
- Golden set com cinco casos sintéticos revisados e limitações causais explícitas.

### API e ciclo de feedback

- API FastAPI com recomendações, feedback, health, readiness, métricas e Swagger.
- Persistência SQLite transacional para decisões e feedback, incluindo idempotência,
  conflito terminal e validação do vínculo com a recomendação original.
- Modos `approved` e `adaptive_demo`, com rollback para a política fixa quando a candidata
  adaptativa não estiver aprovada ou disponível.
- Logs estruturados sem payload pessoal e instrumentação OpenTelemetry para métricas e
  traces da API.

### Contêineres e orquestração

- `Containerfile` multi-stage para API, jobs do pipeline, MLflow e Airflow.
- Podman Compose com jobs efêmeros `prepare`, `train`, `evaluate` e `pipeline`, mantendo
  dados, modelos, relatórios e tracking em volumes compartilhados.
- Airflow 3.3 com LocalExecutor, SQLite persistido e DAG visual manual M1 → M2 → M3 → M4,
  incluindo dependências, retries, estado e logs por tarefa.
- Perfis opcionais `jobs` e `orchestration`, portas restritas ao loopback e healthchecks dos
  principais serviços.

### MLOps e reprodutibilidade

- MLflow 3.15 containerizado para parâmetros, métricas e artefatos dos experimentos M3/M4.
- Configuração de hosts permitidos e worker único para compatibilidade local com Podman e
  Windows.
- Compartilhamento seguro de artefatos entre MLflow, jobs e Airflow usando UID 50000,
  grupo compartilhado e diretórios com `setgid`.
- Rebase portátil das URIs absolutas do MLflow após clone ou inicialização de volume.
- Job `mlflow-snapshot` para publicar atomicamente o SQLite e os artefatos do volume no
  checkout, recusando runs ativos e validando os ponteiros finais de M3/M4.
- Snapshot atual sincronizado com 24 runs e 125 arquivos; os runs finais M3 e M4 estão
  finalizados e possuem parâmetros, métricas e artefatos reabríveis.

### Observabilidade

- Stack open source com Prometheus, Grafana, Loki, Tempo, Grafana Alloy, OpenTelemetry
  Collector e Alertmanager.
- Dashboards provisionados para sinais RED da API, feedback, política online, métricas
  offline, gates técnicos e disponibilidade dos artefatos.
- Exportador do processo M1–M5, regras de gravação e alertas para indisponibilidade,
  readiness, evidências ausentes, gate reprovado e queda de recompensa.
- Correlação de logs e traces por `trace_id`, persistência local em volumes e runbook de
  operação com Podman Compose.

### Documentação, governança e qualidade

- README consolidado com problema de negócio, fonte Kaggle, licença, EDA, preparação,
  resultados, golden set, API, MLflow, observabilidade, arquitetura AWS e comandos de
  reprodução.
- Contrato de decisão, elegibilidade, retenção, minimização, humano no loop, riscos e
  rollback documentados e versionados.
- Arquitetura-alvo AWS cobrindo API Gateway/WAF, ECS Fargate, ECR, DynamoDB, S3, RDS,
  SageMaker/ECS Jobs, CloudWatch, IAM, KMS, Secrets Manager e CloudTrail.
- Suíte unitária e de integração para dados, modelo, políticas, API, observabilidade,
  contêineres, Airflow, rebase e snapshot MLflow.
- CI em Linux com lint, testes, verificação do hash da fonte e validação da coerência do
  snapshot MLflow versionado.

### Correções relevantes

- Corrigida a rejeição de `Host` do MLflow ao acessar `localhost:5000` pelo host.
- Corrigida a inicialização do MLflow quando runs falhos não possuem diretório de
  artefatos.
- Corrigidas permissões de escrita no volume compartilhado do MLflow para jobs e Airflow.
- Corrigida a divergência entre `latest_mlflow_run.json`, `mlflow.db` e `mlruns/` após
  execuções realizadas dentro dos contêineres.
