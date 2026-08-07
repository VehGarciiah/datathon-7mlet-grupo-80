ARG PYTHON_VERSION=3.14.6

FROM docker.io/library/python:${PYTHON_VERSION}-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 datathon \
    && useradd --uid 10001 --gid datathon --create-home --shell /usr/sbin/nologin datathon

COPY requirements-api.txt ./
RUN python -m pip install --no-cache-dir -r requirements-api.txt

COPY src ./src
COPY configs ./configs
COPY artifacts/models ./artifacts/models
COPY artifacts/policies ./artifacts/policies
COPY reports/modeling ./reports/modeling
COPY reports/policy ./reports/policy
COPY reports/serving ./reports/serving
COPY observability/api/entrypoint.sh /usr/local/bin/datathon-api-entrypoint

RUN mkdir -p /app/artifacts/serving /var/log/datathon \
    && chown -R datathon:datathon /app/artifacts/serving /var/log/datathon \
    && chmod 0755 /usr/local/bin/datathon-api-entrypoint

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=4 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)" || exit 1

ENTRYPOINT ["/usr/local/bin/datathon-api-entrypoint"]
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]


FROM docker.io/library/python:${PYTHON_VERSION}-slim AS mlflow

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m pip install --no-cache-dir mlflow==3.15.1

COPY mlflow.db /seed/mlflow.db
COPY mlruns /seed/mlruns
COPY scripts/rebase_mlflow_paths.py /app/scripts/rebase_mlflow_paths.py
COPY observability/mlflow/entrypoint.sh /usr/local/bin/datathon-mlflow-entrypoint

RUN chmod 0755 /usr/local/bin/datathon-mlflow-entrypoint

EXPOSE 5000

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)" || exit 1

ENTRYPOINT ["/usr/local/bin/datathon-mlflow-entrypoint"]
