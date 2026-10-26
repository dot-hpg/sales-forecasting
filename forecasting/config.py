"""Project-wide paths and constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models"
FIGURE_DIR = ROOT / "reports" / "figures"

TRAIN_FILE = RAW_DIR / "TRAIN.csv"
TEST_FILE = RAW_DIR / "TEST_FINAL.csv"
MODEL_FILE = MODEL_DIR / "lgbm_sales_forecaster.joblib"
METADATA_FILE = MODEL_DIR / "model_metadata.json"
HISTORY_FILE = PROCESSED_DIR / "sales_history.parquet"

# The test period (2019-06-01 to 2019-07-31) is 61 days long, so every lag-based
# feature looks back at least 61 days. The model never needs a sales value that
# would be unknown at forecast time inside one 61-day block.
HORIZON = 61
SAME_WEEKDAY_LAGS = [63, 70, 77, 84, 91]  # multiples of 7 that are >= HORIZON
EXTRA_LAGS = [61, 364]                    # most recent usable day, same day last year
ROLLING_WINDOWS = [7, 28, 91]             # rolling means, shifted by HORIZON

CATEGORICAL = ["Store_Type", "Location_Type", "Region_Code"]
TARGET = "Sales"
