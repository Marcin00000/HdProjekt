# Instrukcja użytkownika — aplikacja webowa

Dokument opisuje obsługę portalu FastAPI uruchamianego przez Docker (`docker compose up`) lub lokalnie (`python scripts/run.py app --serve`).

## Adresy usług

| Usługa | URL (Docker) | URL (lokalnie) |
|--------|--------------|----------------|
| Portal | http://localhost:8080 | http://127.0.0.1:8000 |
| MLflow | http://localhost:5000 | http://127.0.0.1:5000 |
| Prefect | http://localhost:4200 | http://127.0.0.1:4200 |

## Strony portalu

### Strona główna (`/`)

Centralny punkt nawigacji do modułów: dashboard, prognoza, dokumentacja operacji, monitoring, link do MLflow.

### Dashboard (`/dashboard`)

Wyświetla wykresy i tabele:

- średnia pensja wg lokalizacji,
- rozkład wykształcenia,
- udział pracy zdalnej.

Źródło danych zależy od konfiguracji:

| Źródło | Warunek |
|--------|---------|
| Azure SQL | Poprawny `.env` i wcześniejsze załadowanie hurtowni |
| Silver lokalny | Istnieje `data/processed/cleaned.parquet` |
| Gold | Istnieje `data/processed/salary_by_location.parquet` |

Przycisk odświeżenia pobiera dane z API `/api/dashboard`.

### Prognoza pensji (`/predict`)

Formularz webowy z polami zgodnymi z modelem (stanowisko, doświadczenie, branża itd.). Wynik to szacowana pensja w USD. Każda prognoza może być zapisywana w `data/processed/prediction_log.jsonl` (audyt, nie używany do wykrywania driftu danych).

Równoważne wywołanie API:

```http
POST /predict
Content-Type: application/json

{
  "job_title": "Data Scientist",
  "experience_years": 5,
  "education_level": "Master",
  "skills_count": 10,
  "industry": "Technology",
  "company_size": "Medium",
  "location": "USA",
  "remote_work": "Yes",
  "certifications": 2
}
```

### Dokumentacja ETL (`/docs/etl`)

Umożliwia uruchomienie zadań w tle:

| Przycisk / zadanie | Efekt |
|--------------------|-------|
| Przygotuj dane | CSV → silver + gold lokalnie |
| Przygotuj + lake | Dodatkowy zapis do Azure Data Lake |
| Załaduj hurtownię SQL | Schemat gwiazdy → Azure SQL |
| Uruchom ETL (Prefect) | Pełny flow `etl_main` |
| ETL bez SQL | Flow bez ładowania hurtowni |

### Dokumentacja treningu (`/docs/training`)

| Operacja | Opis |
|----------|------|
| Uruchom trening | Pełny trening z tuningiem (jeśli włączony w `params.yaml`) |
| Trening szybki | Trening bez siatki hiperparametrów |
| Przeładuj model | Odświeżenie modelu w API po zapisie plików |

Trening zapisuje modele w `models/` oraz `training_baseline.parquet` (referencja monitoringu).

### Dokumentacja DVC (`/docs/dvc`)

| Operacja | Opis |
|----------|------|
| DVC repro | Etapy `prepare` → `train` |
| DVC repro (szybki) | Bez tuningu hiperparametrów |
| DVC repro + push | Reprodukcja i wysyłka na remote Azure |
| DVC push | Wysyłka artefaktów bez pełnej reprodukcji |

### Monitoring (`/monitoring`)

Moduł wykrywania zmian rozkładu danych (drift) między:

- **referencją** — `training_baseline.parquet` (stan z treningu),
- **bieżącym rynkiem** — `cleaned.parquet` lub symulacja.

| Akcja | Opis |
|-------|------|
| Symuluj zmianę rynku | Tworzy `silver_current_simulated.parquet` (scenariusze np. `salary_market_up`) |
| Generuj raport driftu | Raport HTML w `reports/`, metryki w `drift_metrics.json` |
| Wyczyść symulację | Przywraca porównanie z rzeczywistym `cleaned.parquet` |
| Sprawdź drift i retrenuj | Przy alarmie driftu uruchamia trening i przeładowuje model |

Do wykrywania driftu **nie** wykorzystuje się pojedynczych wpisów z `prediction_log.jsonl` — porównywane są zbiory reprezentujące rynek, nie pojedyncze prognozy z formularza.

## Zadania w tle

Operacje z paneli uruchamiane są asynchronicznie (jedno aktywne zadanie naraz). Status:

- `GET /api/system/status` — zajętość runnera, dostępność plików i modelu,
- `GET /api/jobs/{id}` — log i postęp zadania.

Typy zadań (`POST /api/jobs` z polem `job_type`):

`prepare`, `prepare_lake`, `load_dwh`, `etl`, `etl_skip_sql`, `train`, `train_fast`, `dvc_repro`, `dvc_repro_fast`, `dvc_repro_push`, `dvc_push`, `simulate_drift`, `drift_report`, `clear_drift_simulation`, `check_drift_retrain`.

Po treningu lub retreningu model w API jest przeładowywany automatycznie.

## Przypadki użycia

### Przypadek 1: Pierwsze uruchomienie od zera

1. Uruchomić kontener: `docker compose up --build`.
2. Na `/docs/etl` — **Przygotuj dane** (wymagany CSV lub dane w lake).
3. Na `/docs/training` — **Trening szybki**.
4. Na `/predict` — wprowadzić przykładową ofertę i sprawdzić wynik.
5. Na `/dashboard` — zweryfikować wykresy (po załadowaniu SQL lub z silver).

### Przypadek 2: Aktualizacja danych i hurtowni

1. Wgrać nowy CSV do lake lub zastąpić plik lokalny.
2. Uruchomić **ETL (Prefect)** z `/docs/etl`.
3. Uruchomić **Załaduj hurtownię SQL** (jeśli używany dashboard SQL).
4. Odświeżyć `/dashboard`.

### Przypadek 3: Monitoring zmian rynku

1. Upewnić się, że wykonano trening (istnieje baseline).
2. Na `/monitoring` — **Symuluj zmianę rynku** (scenariusz `salary_market_up`).
3. **Generuj raport driftu** — sprawdzić `drift_alert` w metrykach.
4. Przy alarmie — **Sprawdź drift i retrenuj**.
5. Zweryfikować nowy run w MLflow i prognozę na `/predict`.

### Przypadek 4: Reprodukcja eksperymentu w zespole

1. `git pull` i `dvc pull` na maszynie lokalnej.
2. Na `/docs/dvc` — **DVC repro** lub **szybki**.
3. Porównać metryki w MLflow i `data/processed/metrics.json`.

### Przypadek 5: Tylko API bez formularza

1. Uruchomić aplikację (`docker compose up` lub `run.py app --serve`).
2. Wywołać `GET /health` — potwierdzenie załadowania modelu.
3. Wywołać `POST /predict` zgodnie ze schematem OpenAPI (`/docs`).

## Rozwiązywanie problemów

| Objaw | Możliwa przyczyna | Działanie |
|-------|-------------------|-----------|
| Dashboard pusty | Brak danych SQL lub silver | Wykonać przygotowanie danych lub `load_dwh` |
| Błąd prognozy | Brak modelu | Trening lub `dvc pull` |
| Raport driftu bez baseline | Brak treningu | Uruchomić trening |
| Brak alertu po symulacji | Za mała próbka lub słaby scenariusz | Zwiększyć `default_simulate_count` lub użyć `salary_features_combo` |
| Zadanie „wisi” | Inne zadanie w toku | Sprawdzić `/api/system/status` |

Powiązane dokumenty: [configuration.md](configuration.md), [tools.md](tools.md), [user-cli.md](user-cli.md).
