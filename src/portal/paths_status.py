"""Status plikow danych — lokalnie i Azure."""

from __future__ import annotations

from src.config import PROJECT_ROOT, find_local_raw_csv
from src.portal.data_loader import GOLD_BY_LOCATION, SILVER_PATH
from src.portal.model_artifacts import (
    MODEL_PATH,
    PREPROCESSOR_PATH,
    joblib_looks_valid,
)

GOLD_BY_LOCATION_INDUSTRY = PROJECT_ROOT / "data" / "processed" / "salary_by_location_industry.parquet"


def azure_storage_configured() -> bool:
    try:
        from src.config import AzureStorageConfig

        AzureStorageConfig()
        return True
    except ValueError:
        return False


def get_paths_status() -> dict[str, bool]:
    local_raw = find_local_raw_csv() is not None
    azure_ok = azure_storage_configured()
    gold_complete = GOLD_BY_LOCATION.is_file() and GOLD_BY_LOCATION_INDUSTRY.is_file()
    return {
        "raw_csv": local_raw or azure_ok,
        "raw_csv_local": local_raw,
        "raw_csv_azure": azure_ok and not local_raw,
        "silver": SILVER_PATH.is_file(),
        "gold": gold_complete,
        "preprocessor": joblib_looks_valid(PREPROCESSOR_PATH),
        "model": joblib_looks_valid(MODEL_PATH),
    }
