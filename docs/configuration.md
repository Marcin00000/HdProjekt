# Konfiguracja środowiska

Dokument opisuje wymagania infrastrukturalne, pliki konfiguracyjne i sposób weryfikacji poprawności ustawień.

## Azure Data Lake (Storage Account)

### Utworzenie zasobów

1. W [Azure Portal](https://portal.azure.com) utworzyć **Storage account** z włączonym **hierarchical namespace** (ADLS Gen2).
2. Utworzyć kontener, np. `job-data`.
3. Utworzyć foldery: `raw/`, `silver/`, `gold/`, `dvc-artifacts/`.
4. Wgrać plik CSV do `raw/job_salary_prediction_dataset.csv` (portal Azure, AzCopy lub `python scripts/verify.py --azure --upload-raw`).
5. Skopiować **Access keys** do pliku `.env`.

### Zmienne środowiskowe (Data Lake)

| Zmienna | Opis |
|---------|------|
| `AZURE_STORAGE_ACCOUNT_NAME` | Nazwa konta storage |
| `AZURE_STORAGE_ACCOUNT_KEY` | Klucz dostępu |
| `AZURE_STORAGE_CONTAINER` | Kontener (domyślnie `job-data`) |
| `AZURE_LAKE_RAW_PATH` | Ścieżka pliku surowego |
| `AZURE_LAKE_SILVER_PATH` | Ścieżka silver parquet |
| `AZURE_LAKE_GOLD_PATH` | Ścieżka agregatu gold |
| `AZURE_DVC_CONTAINER` | Podfolder na artefakty DVC (`dvc-artifacts`) |
| `LOCAL_RAW_DATA_PATH` | Lokalna ścieżka CSV przed uploadem |

## Azure SQL Database

### Utworzenie bazy

1. Utworzyć **Azure SQL Database** z serwerem SQL i kontem administratora.
2. W sekcji **Networking** włączyć dostęp z Azure oraz dodać adres IP klienta (firewall).
3. Zainstalować na maszynie lokalnej **ODBC Driver 18 for SQL Server**.

### Zmienne środowiskowe (SQL)

| Zmienna | Opis |
|---------|------|
| `AZURE_SQL_SERVER` | Host serwera, np. `nazwa.database.windows.net` |
| `AZURE_SQL_DATABASE` | Nazwa bazy |
| `AZURE_SQL_USER` | Login SQL |
| `AZURE_SQL_PASSWORD` | Hasło |

Opcjonalnie można ustawić pełny URI w `AZURE_SQL_CONNECTION_STRING` (nadpisuje pola powyżej).

## Plik `.env`

Wzór znajduje się w `.env.example`. Plik `.env` nie jest commitowany do Git.

```powershell
copy .env.example .env
```

Po uzupełnieniu zmiennych:

```powershell
python scripts/verify.py --env --azure --sql
```

## DVC remote (Azure)

Po instalacji pakietów (`python scripts/install.py`) i konfiguracji Storage:

```powershell
python scripts/verify.py --dvc
```

Remote `azure_remote` wskazuje na `azure://<kontener>/<dvc-artifacts>`. Poświadczenia zapisywane są w `.dvc/config.local` (poza repozytorium Git).

## Plik `params.yaml`

Centralny plik parametrów śledzony przez DVC i używany przez portal.

| Sekcja | Zastosowanie |
|--------|--------------|
| `prepare` | Progi czyszczenia danych (kwantyle pensji, max. lata doświadczenia) |
| `test_size`, `random_state` | Podział zbioru treningowego |
| `n_estimators`, `max_depth`, … | Domyślne hiperparametry XGBoost |
| `dvc.fast_train` | Pominięcie tuningu przy `dvc repro` |
| `tuning` | Siatka GridSearchCV |
| `monitoring` | Progi driftu, rozmiary próbek, tryb retreningu |

Przykład sekcji monitoringu:

```yaml
monitoring:
  drift_threshold: 0.5
  min_current_rows: 1000
  default_simulate_count: 5000
  retrain_mode: fast
  auto_retrain_enabled: false
```

Gdy `auto_retrain_enabled: true`, harmonogram Prefect (`monitor_and_retrain`) może uruchamiać retrening bez interwencji użytkownika.

## Docker Compose

Plik `docker-compose.yml` uruchamia jeden kontener aplikacji z mapowaniem portów:

| Port hosta | Usługa |
|------------|--------|
| 8080 | Portal FastAPI |
| 5000 | MLflow UI |
| 4200 | Prefect Server |

Wolumeny montowane na hoście:

| Wolumen | Zawartość |
|---------|-----------|
| `./models` | Modele `.joblib` |
| `./data/mlflow` | Baza SQLite MLflow |
| `./data/prefect` | Historia Prefect |
| `./data/processed` | Parquet, metryki, baseline |
| `./reports` | Raporty HTML Evidently |
| `./params.yaml` | Parametry (tylko odczyt) |

Opcjonalnie można zamontować plik CSV:

```yaml
volumes:
  - ./job_salary_prediction_dataset.csv:/app/job_salary_prediction_dataset.csv:ro
```

Zmienne z `.env` są ładowane przez `env_file` w compose (plik nie jest wymagany do startu kontenera, lecz potrzebny do operacji Azure).

## Artefakty podsumowań operacji

Po uruchomieniu pipeline w katalogu `data/processed/` powstają m.in.:

| Plik | Znaczenie |
|------|-----------|
| `cleaned.parquet` | Warstwa silver |
| `prepare_summary.json` | Podsumowanie czyszczenia |
| `dwh_summary.json` | Podsumowanie ładowania hurtowni |
| `etl_summary.json` | Podsumowanie flow Prefect |
| `training_summary.json` | Metryki ostatniego treningu |
| `training_baseline.parquet` | Referencja dla monitoringu driftu |
| `drift_metrics.json` | Wynik ostatniego raportu Evidently |
| `metrics.json` | Metryki DVC (RMSE, MAE, R²) |

Katalog `data/processed/` jest wyłączony z Git (`.gitignore`).

## Weryfikacja kompletna

```powershell
python scripts/verify.py --all
```

Obejmuje: plik `.env`, pliki projektu, Azure Data Lake, Azure SQL, konfigurację DVC oraz obecność eksperymentu MLflow.

## Koszty Azure

Zasoby testowe generują koszty w ramach subskrypcji. Zaleca się monitorowanie w **Cost Management** i usunięcie lub zatrzymanie zasobów po zakończeniu prac.
