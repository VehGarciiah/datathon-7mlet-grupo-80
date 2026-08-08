#!/bin/sh
set -eu

mkdir -p /mlflow/mlruns

if [ ! -f /mlflow/mlflow.db ]; then
    cp /seed/mlflow.db /mlflow/mlflow.db
fi

if [ -z "$(find /mlflow/mlruns -mindepth 1 -print -quit)" ]; then
    cp -R /seed/mlruns/. /mlflow/mlruns/
fi

python /app/scripts/rebase_mlflow_paths.py \
    --database /mlflow/mlflow.db \
    --artifacts-root /mlflow/mlruns

# Os jobs de pipeline e o Airflow usam UID 50000 e GID 0. O bit setgid mantém
# os novos diretórios no grupo compartilhado sem liberar escrita global.
chmod -R g+rwX /mlflow/mlruns
find /mlflow/mlruns -type d -exec chmod g+s {} +

exec python -m mlflow server \
    --backend-store-uri sqlite:////mlflow/mlflow.db \
    --default-artifact-root /mlflow/mlruns \
    --host 0.0.0.0 \
    --port 5000 \
    --workers "${MLFLOW_SERVER_WORKERS:-1}"
