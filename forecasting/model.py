"""The production forecaster: a global LightGBM model over all stores.

It is trained on log1p(Sales) so that errors are relative (a 1,000 miss matters
more for a small store than a large one) and predicts in blocks of ``HORIZON``
days. When asked for more than one block, it feeds its own predictions back in
as history, so it can forecast any horizon.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import HORIZON, METADATA_FILE, MODEL_FILE
from .features import FEATURES, build_features

LGBM_PARAMS = dict(
    objective="regression",
    learning_rate=0.03,
    n_estimators=1500,
    num_leaves=63,
    min_child_samples=40,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    random_state=42,
    verbose=-1,
)

PANEL_COLUMNS = ["Store_id", "Store_Type", "Location_Type", "Region_Code",
                 "Date", "Holiday", "Discount", "Sales"]


def training_rows(feat: pd.DataFrame) -> pd.DataFrame:
    """Rows usable for training: known, non-zero sales (zero = store closed)."""
    return feat[feat["Sales"].notna() & (feat["Sales"] > 0)]


@dataclass
class SalesForecaster:
    params: dict = field(default_factory=lambda: dict(LGBM_PARAMS))
    model: lgb.LGBMRegressor | None = None
    features: list = field(default_factory=lambda: list(FEATURES))
    last_train_date: pd.Timestamp | None = None

    # ------------------------------------------------------------------ fit
    def fit(self, history: pd.DataFrame, feat: pd.DataFrame | None = None) -> "SalesForecaster":
        feat = build_features(history[PANEL_COLUMNS]) if feat is None else feat
        rows = training_rows(feat)
        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(rows[self.features], np.log1p(rows["Sales"]))
        self.last_train_date = history["Date"].max()
        return self

    def predict_features(self, feat: pd.DataFrame) -> np.ndarray:
        return np.expm1(self.model.predict(feat[self.features])).clip(min=0)

    # ------------------------------------------------------------- forecast
    def forecast(self, history: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
        """Forecast Sales for every row of ``future``.

        history: past rows with Sales (any stores; at least ~1 year is ideal).
        future:  rows with Store_id, store attributes, Date, Holiday, Discount.
        Returns ``future`` with a ``Forecast`` column.
        """
        hist = history[PANEL_COLUMNS].copy()
        fut = future.copy()
        fut["Sales"] = np.nan
        panel = pd.concat([hist, fut[PANEL_COLUMNS]], ignore_index=True)
        panel = panel.drop_duplicates(["Store_id", "Date"], keep="last")
        panel = panel.sort_values(["Store_id", "Date"]).reset_index(drop=True)

        start = hist["Date"].max() + pd.Timedelta(days=1)
        end = fut["Date"].max()
        while start <= end:
            block_end = start + pd.Timedelta(days=HORIZON - 1)
            feat = build_features(panel)
            mask = (feat["Date"] >= start) & (feat["Date"] <= block_end) & feat["Sales"].isna()
            if mask.any():
                preds = self.predict_features(feat.loc[mask])
                key = feat.loc[mask, ["Store_id", "Date"]].assign(_pred=preds)
                panel = panel.merge(key, on=["Store_id", "Date"], how="left")
                panel["Sales"] = panel["Sales"].fillna(panel.pop("_pred"))
            start = block_end + pd.Timedelta(days=1)

        out = fut.drop(columns="Sales").merge(
            panel[["Store_id", "Date", "Sales"]].rename(columns={"Sales": "Forecast"}),
            on=["Store_id", "Date"], how="left")
        return out

    # ------------------------------------------------------------ persist
    def save(self, path=MODEL_FILE, metadata: dict | None = None, metadata_path=METADATA_FILE):
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        if metadata is not None:
            metadata_path.write_text(json.dumps(metadata, indent=2, default=str))

    @staticmethod
    def load(path=MODEL_FILE) -> "SalesForecaster":
        return joblib.load(path)
