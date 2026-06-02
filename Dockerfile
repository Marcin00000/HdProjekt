FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    git \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi>=0.110.0 \
    "uvicorn[standard]>=0.27.0" \
    python-multipart>=0.0.9 \
    jinja2>=3.1.0 \
    pydantic>=2.0.0 \
    pandas>=2.0.0 \
    pyarrow>=14.0.0 \
    scikit-learn>=1.4.0 \
    xgboost>=2.0.0 \
    joblib>=1.3.0 \
    python-dotenv>=1.0.0 \
    pyyaml>=6.0.0 \
    sqlalchemy>=2.0.0 \
    mlflow>=2.10.0 \
    dvc>=3.0.0 \
    "dvc[azure]" \
    prefect>=2.14.0 \
    adlfs>=2024.0.0 \
    pyodbc>=5.0.0

COPY src/ ./src/
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY params.yaml ./
COPY dvc.yaml ./
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY docker/start_mlflow_background.py /app/docker/start_mlflow_background.py
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

# Modele montowane z hosta (DVC pull); pusty katalog na build
RUN mkdir -p /app/models /app/data/mlflow /app/data/processed

ENV PYTHONPATH=/app
ENV PORT=8000
ENV MLFLOW_PORT=5000
ENV MLFLOW_PUBLIC_URL=http://127.0.0.1:5000

EXPOSE 8000 5000

ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
