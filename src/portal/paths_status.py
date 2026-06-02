"""Status plikow danych — lokalnie i Azure."""

from __future__ import annotations

from src.config import PROJECT_ROOT, local_raw_data_path

MODEL_PATH = PROJECT_ROOT / "models" / "xgboost_model.joblib"
PREPROCESSOR_PATH = PROJECT_ROOT / "models" / "preprocessor.joblib"
from src.portal.data_loader import GOLD_BY_LOCATION, SILVER_PATH


def azure_storage_configured() -> bool:
    try:
        from src.config import AzureStorageConfig

        AzureStorageConfig()
        return True
    except ValueError:
        return False


def get_paths_status() -> dict[str, bool]:
    local_raw = local_raw_data_path().is_file()
    azure_ok = azure_storage_configured()
    return {
        "raw_csv": local_raw or azure_ok,
        "raw_csv_local": local_raw,
        "raw_csv_azure": azure_ok and not local_raw,
        "silver": SILVER_PATH.is_file(),
        "gold": GOLD_BY_LOCATION.is_file(),
        "preprocessor": PREPROCESSOR_PATH.is_file(),
        "model": MODEL_PATH.is_file(),
    }
