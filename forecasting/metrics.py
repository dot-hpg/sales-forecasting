"""Forecast accuracy metrics."""
import numpy as np
import pandas as pd


def evaluate(y_true, y_pred, name: str = "model") -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    nz = y_true > 0  # MAPE is undefined on closure days with zero sales
    return {
        "model": name,
        "MAE": np.mean(np.abs(err)),
        "RMSE": np.sqrt(np.mean(err ** 2)),
        "MAPE_%": 100 * np.mean(np.abs(err[nz]) / y_true[nz]),
        "WAPE_%": 100 * np.abs(err).sum() / np.abs(y_true).sum(),
        "R2": 1 - np.sum(err ** 2) / np.sum((y_true - y_true.mean()) ** 2),
    }


def metrics_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).set_index("model").round(3).sort_values("RMSE")
