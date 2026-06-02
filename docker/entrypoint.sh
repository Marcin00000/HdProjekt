#!/bin/sh
set -e

export PYTHONPATH="${PYTHONPATH:-/app}"
PORT="${PORT:-8000}"
MLFLOW_PORT="${MLFLOW_PORT:-5000}"
PREFECT_PORT="${PREFECT_PORT:-4200}"
export PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:${PREFECT_PORT}/api}"
export PREFECT_SERVER_ANALYTICS_ENABLED="${PREFECT_SERVER_ANALYTICS_ENABLED:-false}"
export GIT_PYTHON_REFRESH="${GIT_PYTHON_REFRESH:-quiet}"

if [ -f /app/.dvc/config ]; then
  python -m dvc config core.no_scm true 2>/dev/null || true
fi

echo "Uruchamianie Prefect Server na porcie ${PREFECT_PORT}..."
python /app/docker/start_prefect_background.py &
sleep 3

if [ -f /app/data/mlflow/mlflow.db ]; then
  echo "Uruchamianie MLflow UI na porcie ${MLFLOW_PORT}..."
  python /app/docker/start_mlflow_background.py &
else
  echo "Brak data/mlflow/mlflow.db — MLflow UI pominiety (uruchom trening lub zamontuj wolumen)."
fi

echo "Uruchamianie portalu FastAPI na porcie ${PORT}..."
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT}"
