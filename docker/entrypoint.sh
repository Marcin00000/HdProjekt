#!/bin/sh
set -e

export PYTHONPATH="${PYTHONPATH:-/app}"
PORT="${PORT:-8000}"
MLFLOW_PORT="${MLFLOW_PORT:-5000}"

if [ -f /app/data/mlflow/mlflow.db ]; then
  echo "Uruchamianie MLflow UI na porcie ${MLFLOW_PORT}..."
  python /app/docker/start_mlflow_background.py &
else
  echo "Brak data/mlflow/mlflow.db — MLflow UI pominiety (uruchom trening lub zamontuj wolumen)."
fi

echo "Uruchamianie portalu FastAPI na porcie ${PORT}..."
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT}"
