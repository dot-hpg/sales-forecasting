"""Train the final forecaster and export every artefact the app, API and Tableau use.

Run from the repository root:
    python scripts/train.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecasting import SalesForecaster, build_features, evaluate, load_train_test, store_master  # noqa: E402
from forecasting.config import HISTORY_FILE, HORIZON, METADATA_FILE, MODEL_FILE, PROCESSED_DIR  # noqa: E402
from forecasting.model import PANEL_COLUMNS  # noqa: E402


def _round(df: pd.DataFrame, digits: int = 2) -> pd.DataFrame:
    floats = df.select_dtypes("float").columns
    return df.assign(**{c: df[c].round(digits) for c in floats})


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    train, test = load_train_test()

    # 1. Honest hold-out: the last 61 days, forecast exactly as in production.
    cutoff = train["Date"].max() - pd.Timedelta(days=HORIZON - 1)
    hist, hold = train[train["Date"] < cutoff], train[train["Date"] >= cutoff]
    holdout_model = SalesForecaster().fit(hist)
    val = holdout_model.forecast(hist, hold.drop(columns=["Sales", "Orders"]))
    val = val.merge(hold[["Store_id", "Date", "Sales"]], on=["Store_id", "Date"])
    scores = evaluate(val["Sales"], val["Forecast"], "LightGBM (store-day)")
    daily = val.groupby("Date")[["Sales", "Forecast"]].sum()
    daily_scores = evaluate(daily["Sales"], daily["Forecast"], "LightGBM (chain-day)")
    print(json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in scores.items()}, indent=2))

    # 2. Final model on all 516 days.
    model = SalesForecaster().fit(train)
    forecast = model.forecast(train, test)

    importance = (pd.Series(model.model.booster_.feature_importance("gain"), index=model.features)
                  .sort_values(ascending=False))
    importance = (100 * importance / importance.sum()).round(2)

    metadata = {
        "model": "LightGBM global model on log1p(Sales)",
        "trained_on": f"{train['Date'].min().date()} to {train['Date'].max().date()}",
        "rows": int(len(train)),
        "stores": int(train["Store_id"].nunique()),
        "horizon_days": HORIZON,
        "holdout_period": f"{cutoff.date()} to {train['Date'].max().date()}",
        "holdout_store_day": {k: float(v) for k, v in scores.items() if k != "model"},
        "holdout_chain_day": {k: float(v) for k, v in daily_scores.items() if k != "model"},
        "features": model.features,
        "feature_importance_gain_pct": importance.to_dict(),
        "params": model.params,
    }
    model.save(MODEL_FILE, metadata, METADATA_FILE)

    # 3. Exports for the app, the API and Tableau.
    train[PANEL_COLUMNS + ["Orders"]].to_parquet(HISTORY_FILE, index=False)
    stores = store_master(train)
    stats = train.groupby("Store_id").agg(
        avg_daily_sales=("Sales", "mean"), total_sales=("Sales", "sum"),
        avg_daily_orders=("Orders", "mean"), discount_days_pct=("Discount", "mean"))
    stats["discount_days_pct"] *= 100
    stores.merge(stats.round(2), on="Store_id").to_csv(PROCESSED_DIR / "store_master.csv", index=False)

    clean = train.copy()
    clean["Avg_Order_Value"] = (clean["Sales"] / clean["Orders"].replace(0, np.nan)).round(2)
    clean["Weekday"] = clean["Date"].dt.day_name()
    clean["Month"] = clean["Date"].dt.to_period("M").astype(str)
    clean["Is_Weekend"] = (clean["Date"].dt.dayofweek >= 5).astype(int)
    clean["Discount_Flag"] = clean["Discount"].map({1: "Yes", 0: "No"})
    clean["Holiday_Flag"] = clean["Holiday"].map({1: "Holiday", 0: "Working day"})
    clean.to_csv(PROCESSED_DIR / "sales_clean.csv", index=False, date_format="%Y-%m-%d")

    val_out = val[["Store_id", "Store_Type", "Location_Type", "Region_Code", "Date",
                   "Holiday", "Discount", "Sales", "Forecast"]].copy()
    val_out["Error"] = val_out["Forecast"] - val_out["Sales"]
    val_out["Abs_Pct_Error"] = (100 * val_out["Error"].abs() / val_out["Sales"].replace(0, np.nan)).round(2)
    _round(val_out).to_csv(PROCESSED_DIR / "holdout_predictions.csv", index=False, date_format="%Y-%m-%d")

    fc_out = forecast[["ID", "Store_id", "Store_Type", "Location_Type", "Region_Code",
                       "Date", "Holiday", "Discount", "Forecast"]]
    fc_out = _round(fc_out)
    fc_out.to_csv(PROCESSED_DIR / "test_forecast.csv", index=False, date_format="%Y-%m-%d")

    timeline = pd.concat([
        train.assign(Type="Actual")[["Store_id", "Store_Type", "Location_Type", "Region_Code",
                                     "Date", "Holiday", "Discount", "Sales", "Type"]],
        fc_out.rename(columns={"Forecast": "Sales"}).assign(Type="Forecast").drop(columns="ID"),
    ])
    timeline["Discount"] = timeline["Discount"].map({1: "Yes", 0: "No"})
    _round(timeline).to_csv(PROCESSED_DIR / "actual_and_forecast.csv", index=False, date_format="%Y-%m-%d")
    importance.rename("gain_pct").rename_axis("feature").to_csv(PROCESSED_DIR / "feature_importance.csv")
    print(f"Saved model to {MODEL_FILE.relative_to(MODEL_FILE.parents[1])} and exports to data/processed/")


if __name__ == "__main__":
    main()
