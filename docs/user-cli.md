# Instrukcja użytkownika — linia poleceń

Dokument opisuje skrypty w katalogu `scripts/` oraz równoważne polecenia używane poza portalem webowym.

## Przegląd skryptów

| Skrypt | Przeznaczenie |
|--------|---------------|
| `install.py` | Instalacja zależności Python |
| `verify.py` | Weryfikacja `.env`, Azure, DVC, MLflow |
| `run.py` | Operacje pipeline i uruchomienie aplikacji |
| `test.py` | Testy automatyczne (pytest) |
| `simulate_drift.py` | Symulacja zmiany rynku (monitoring) |
| `cleanup_project.py` | Usunięcie legacy ścieżek MLflow |
| `reset_mlflow.py` | Reset bazy MLflow i modeli |
| `dvc_prepare.py`, `dvc_train.py` | Etapy wywoływane przez `dvc repro` |

## Instalacja

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python scripts/install.py
```

Opcjonalna inicjalizacja DVC przy pierwszym użyciu:

```powershell
python scripts/install.py --dvc-init
```

## Weryfikacja

```powershell
python scripts/verify.py --env --project
python scripts/verify.py --azure --sql
python scripts/verify.py --dvc
python scripts/verify.py --mlflow
python scripts/verify.py --all
```

| Flaga | Zakres |
|-------|--------|
| `--env` | Obecność pliku `.env` |
| `--project` | Pliki krytyczne repozytorium |
| `--azure` | Połączenie z Data Lake |
| `--upload-raw` | Upload lokalnego CSV do `raw/` |
| `--sql` | Połączenie z Azure SQL |
| `--dvc` | Konfiguracja remote DVC |
| `--mlflow` | Eksperyment i runy w MLflow |
| `--all` | Wszystkie powyższe (bez testu serwera UI) |

## Polecenia `run.py`

```text
python scripts/run.py <subkomenda> [opcje]
```

### `prepare` — czyszczenie i warstwy silver/gold

```powershell
python scripts/run.py prepare
python scripts/run.py prepare --local-only
```

Zapisuje `data/processed/cleaned.parquet`, agregaty gold i `prepare_summary.json`. Bez `--local-only` dane trafiają również do Azure Data Lake.

### `load-dwh` — hurtownia Azure SQL

```powershell
python scripts/run.py load-dwh
python scripts/run.py load-dwh --local-silver
python scripts/run.py load-dwh --build-only
```

Buduje schemat gwiazdy i ładuje tabele do Azure SQL. Flaga `--build-only` pomija zapis do bazy (tylko pliki parquet w `data/dwh/`).

### `etl` — pipeline Prefect

```powershell
python scripts/run.py etl
python scripts/run.py etl --skip-sql
python scripts/run.py etl --serve
```

Flow `etl_main`: raw → silver → gold → SQL (opcjonalnie). Flaga `--serve` rejestruje harmonogram cron (niedziela 03:00). Metryki: `etl_summary.json`.

### `train` — trening XGBoost

```powershell
python scripts/run.py train
python scripts/run.py train --no-tune
```

Wymaga warstwy silver. Rejestruje eksperyment w MLflow, zapisuje modele i `training_summary.json`.

### `dvc` — pipeline DVC

```powershell
python scripts/run.py dvc --setup-dvc
python scripts/run.py dvc --fast
python scripts/run.py dvc --push
python scripts/run.py dvc --stage prepare
```

Odpowiednik `dvc repro` z opcjonalnym push na `azure_remote`.

### `app` — portal FastAPI

```powershell
python scripts/run.py app --serve
python scripts/run.py app --serve --reload --port 8000
python scripts/run.py app --docker
```

`--docker` uruchamia `docker compose up --build`.

### `mlflow-ui` — interfejs MLflow

```powershell
python scripts/run.py mlflow-ui
python scripts/run.py mlflow-ui --port 5001
```

### `drift-simulate` — symulacja driftu

```powershell
python scripts/run.py drift-simulate --scenario salary_market_up --count 5000
```

Równoważne: `python scripts/simulate_drift.py --scenario ... --count ...`

### `drift-retrain` — sprawdzenie driftu i retrening

```powershell
python scripts/run.py drift-retrain
```

Jednorazowe wywołanie `check_drift_and_retrain(manual=True)`. Audyt: `drift_retrain_last.json`.

## Testy

```powershell
python scripts/test.py --smoke
python scripts/test.py --suite api
python scripts/test.py --suite portal
python scripts/test.py --suite monitoring
python scripts/test.py --suite integration
python scripts/test.py --suite all
```

Profil `integration` obejmuje API, portal, monitoring i trening. Profil `all` uruchamia cały katalog `api/tests/`.

## Narzędzia pomocnicze

### Czyszczenie legacy MLflow

```powershell
python scripts/cleanup_project.py
python scripts/cleanup_project.py --mlflow-reset
```

### Reset MLflow

```powershell
python scripts/reset_mlflow.py
python scripts/reset_mlflow.py --train
```

### DVC bezpośrednio

```powershell
dvc repro
dvc repro train
dvc metrics show
dvc pull
dvc push
```

### Harmonogram monitoringu (Prefect)

```powershell
python -m src.monitoring.flows --serve
python -m src.monitoring.flows
```

## Typowa sekwencja (środowisko lokalne)

```powershell
python scripts/install.py
copy .env.example .env
python scripts/verify.py --all

python scripts/run.py prepare
python scripts/run.py load-dwh
python scripts/run.py train --no-tune
python scripts/run.py app --serve

python scripts/test.py --suite all
```

## Przypadki użycia CLI

### Przypadek A: Automatyzacja przygotowania danych

Skrypt CI lub harmonogram uruchamia:

```powershell
python scripts/run.py prepare --local-only
python scripts/run.py etl --skip-sql
```

### Przypadek B: Szybka reprodukcja modelu

```powershell
dvc pull
python scripts/run.py dvc --fast
python scripts/run.py app --serve
```

### Przypadek C: Weryfikacja przed wdrożeniem

```powershell
python scripts/verify.py --all
python scripts/test.py --suite integration
```

### Przypadek D: Demonstracja driftu bez portalu

```powershell
python scripts/run.py train --no-tune
python scripts/run.py drift-simulate --scenario salary_market_up
python scripts/run.py drift-retrain
```

### Przypadek E: Konfiguracja nowej maszyny deweloperskiej

```powershell
python scripts/install.py --dvc-init
python scripts/verify.py --dvc --azure --sql
git pull
dvc pull
```

## Mapowanie ze starszych skryptów

| Wcześniejsze polecenie | Obecne polecenie |
|------------------------|------------------|
| `run_phase1.py` | `run.py prepare` |
| `run_phase2.py` | `run.py load-dwh` |
| `run_phase3.py` | `run.py etl` |
| `run_phase4.py` | `run.py train` |
| `run_phase5.py` | `run.py dvc` |
| `run_phase6/7.py --serve` | `run.py app --serve` |
| `run_mlflow_ui.py` | `run.py mlflow-ui` |
| `setup_azure_check.py` | `verify.py --azure --sql` |
| `setup_dvc_remote.py` | `verify.py --dvc` |
| `run_phase10.py` / pełne testy | `test.py --suite integration` |

Powiązane: [configuration.md](configuration.md), [tools.md](tools.md), [user-web.md](user-web.md).
