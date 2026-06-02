# Prognoza wynagrodzeń — system analityczny (HdProjekt)

Projekt zespołowy na przedmiot **Hurtownie danych i analityczne metody przetwarzania** ([materiały kursu](https://hd-us.netlify.app/), [wymagania zaliczenia](https://hd-us.netlify.app/00-organizacja)).

## Problem biznesowy

Rynek pracy wymaga szybkiego oszacowania pensji na podstawie cech oferty (stanowisko, doświadczenie, branża, lokalizacja, model pracy zdalnej). System łączy hurtownię danych w chmurze, pipeline ETL, model regresji (**XGBoost**), API predykcyjne, dashboard i elementy MLOps (MLflow, DVC, monitoring, CI/CD) — pod ocenę **bdb**.

## Źródło danych

| Pole | Wartość |
|------|---------|
| Zbiór | [Job Salary Prediction Dataset](https://www.kaggle.com/datasets/nalisha/job-salary-prediction-dataset) (Kaggle / autor: nalisha) |
| Pobranie | **Ręczne** (plik CSV w projekcie i w Azure Data Lake `raw/`) |
| Lokalnie | `job_salary_prediction_dataset.csv` (nie w Git — patrz `.gitignore`) |
| W lake | `raw/job_salary_prediction_dataset.csv` |

Kolumny: `job_title`, `experience_years`, `education_level`, `skills_count`, `industry`, `company_size`, `location`, `remote_work`, `certifications`, `salary`.

## Architektura

```mermaid
flowchart LR
  CSV[CSV raw] --> Lake[Azure Data Lake]
  Lake --> Silver[silver parquet]
  Silver --> SQL[Azure SQL DWH]
  Silver --> Train[XGBoost + MLflow]
  Train --> API[FastAPI]
  Train --> DVC[DVC remote]
  SQL --> Dash[Streamlit]
  API --> Evidently[Evidently]
  GHA[GitHub Actions] --> API
```

- **Medallion:** `raw/` → `silver/` → `gold/`
- **Hurtownia:** schemat gwiazdy w Azure SQL
- **ML:** XGBoost, eksperymenty w **lokalnym MLflow** (`./mlruns`)
- **Wersjonowanie artefaktów:** DVC → Azure (`dvc-artifacts/`)

## Wymagania wstępne

- Python 3.11+
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Konto Azure: Storage Account (ADLS Gen2) + Azure SQL Database
- Instrukcja konfiguracji Azure: [docs/azure-setup.md](docs/azure-setup.md)

## Szybki start

```powershell
git clone <url-repozytorium>
cd HdProjekt
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Uzupełnij .env wartościami z Azure Portal (bez cudzysłowów)

python scripts/setup_azure_check.py
python scripts/setup_dvc_remote.py
python scripts/run_phase1.py
python scripts/run_phase2.py
python scripts/run_phase3.py
python scripts/run_phase4.py
python scripts/run_phase5.py --fast   # DVC: prepare + train
python scripts/run_mlflow_ui.py
```

MLflow: `data/mlflow/mlflow.db`. UI: `python scripts/run_mlflow_ui.py`. Pipeline DVC: [docs/dvc-pipeline.md](docs/dvc-pipeline.md).

Orkiestracja Prefect (UI + harmonogram): [docs/prefect-etl.md](docs/prefect-etl.md).

```powershell
# opcjonalnie: prefect server start
python -m src.etl.flows
```

Opcjonalnie upload lokalnego CSV do lake:

```powershell
python scripts/setup_azure_check.py --upload-raw
```

## Struktura katalogów

```
├── src/           # logika (config, etl, cleaning, train, monitoring)
├── scripts/       # setup Azure, DVC
├── docs/          # azure-setup.md
├── data/          # cache lokalny (puste w Git)
├── api/           # FastAPI (faza 6)
├── dashboard/     # Streamlit (faza 7)
├── requirements.txt
└── .env.example
```

Szczegółowy plan faz: `.cursor/plans/projekt_hd_bdb_5389cdd2.plan.md`.

## Rozszerzenia (poza zakresem zaliczenia)

Po ukończeniu projektu możesz **bez zmiany kodu biznesowego** przetestować:

- **Azure ML Workspace** jako backend MLflow — ustaw `MLFLOW_TRACKING_URI` na URI workspace i zarejestruj model w Azure ML Model Registry.
- Harmonogram retrainingu wyłącznie w Prefect (`serve` + cron) zamiast lub obok GitHub Actions.

## Checklist ocena **bdb**

| Element | Status | Dowód (po implementacji) |
|---------|--------|---------------------------|
| Repozytorium Git + README | częściowo | ten plik |
| Azure SQL + dashboard | planowane | `dashboard/`, `src/etl/load_dwh.py` |
| Pipeline ETL (Prefect) | planowane | `src/etl/flows.py` |
| Model + ewaluacja | planowane | XGBoost + MLflow |
| MLflow + DVC + API | częściowo | `data/mlflow/`, `dvc.yaml`, `api/` (faza 6) |
| Monitoring (Evidently) | planowane | `src/monitoring/` |
| CI/CD lub retraining | planowane | `.github/workflows/` lub Prefect cron |

## Autorzy

Zespół projektowy — WNSiT US.
