# Obraz minimalny API. Portal + MLflow: uzyj Dockerfile w katalogu glownym.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
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
    pyyaml>=6.0.0

COPY src/ ./src/
COPY api/ ./api/
COPY models/ ./models/

ENV PYTHONPATH=/app
ENV API_SKIP_MODEL_LOAD=0

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
