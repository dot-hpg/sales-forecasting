"""Flask REST API for the sales forecaster.

Run locally:   python api/app.py            (development server on port 5000)
Production:    gunicorn --chdir api app:app

Endpoints
---------
GET  /health    model status and hold-out accuracy
GET  /stores    the 365 stores and their attributes
POST /predict   forecast sales for one or more (store, date) rows
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecasting import SalesForecaster  # noqa: E402
from forecasting.config import HISTORY_FILE, METADATA_FILE, MODEL_FILE  # noqa: E402

MAX_ROWS = 50_000
MAX_DAYS_AHEAD = 366

app = Flask(__name__)
model = SalesForecaster.load(MODEL_FILE)
metadata = json.loads(METADATA_FILE.read_text())
history = pd.read_parquet(HISTORY_FILE)
history["Date"] = pd.to_datetime(history["Date"])
stores = history.drop_duplicates("Store_id").set_index("Store_id")[["Store_Type", "Location_Type", "Region_Code"]]
last_date = history["Date"].max()


def _flag(value, name: str) -> int:
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"yes", "true", "1"}:
            return 1
        if value in {"no", "false", "0", ""}:
            return 0
    elif value in (0, 1, True, False):
        return int(value)
    raise ValueError(f"'{name}' must be 0/1, true/false or yes/no")


def _parse(rows: list[dict]) -> pd.DataFrame:
    parsed = []
    for i, row in enumerate(rows):
        try:
            store_id = int(row["store_id"])
            date = pd.Timestamp(row["date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {i}: needs a valid 'store_id' and 'date' (YYYY-MM-DD)") from exc
        if store_id not in stores.index:
            raise ValueError(f"row {i}: unknown store_id {store_id} (valid: 1-365)")
        if not last_date < date <= last_date + pd.Timedelta(days=MAX_DAYS_AHEAD):
            raise ValueError(f"row {i}: date must be after {last_date.date()} and at most {MAX_DAYS_AHEAD} days ahead")
        try:
            holiday = _flag(row.get("holiday", 0), "holiday")
            discount = _flag(row.get("discount", 0), "discount")
        except ValueError as exc:
            raise ValueError(f"row {i}: {exc}") from exc
        parsed.append({"Store_id": store_id, **stores.loc[store_id].to_dict(), "Date": date,
                       "Holiday": holiday, "Discount": discount})
    df = pd.DataFrame(parsed)
    if df.duplicated(["Store_id", "Date"]).any():
        raise ValueError("each (store_id, date) pair may appear only once")
    return df


@app.get("/health")
def health():
    return jsonify(status="ok", model=metadata["model"], trained_on=metadata["trained_on"],
                   last_history_date=str(last_date.date()),
                   holdout_wape_pct=round(metadata["holdout_store_day"]["WAPE_%"], 2))


@app.get("/stores")
def list_stores():
    return jsonify(stores.reset_index().to_dict(orient="records"))


@app.post("/predict")
def predict():
    body = request.get_json(silent=True)
    rows = body if isinstance(body, list) else (body or {}).get("rows", [body] if isinstance(body, dict) else None)
    if not rows:
        return jsonify(error="send a JSON object, a list of objects, or {'rows': [...]}"), 400
    if len(rows) > MAX_ROWS:
        return jsonify(error=f"at most {MAX_ROWS} rows per request"), 400
    try:
        future = _parse(rows)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    # Fill the gap between the end of history and the requested dates with the
    # default plan (no holiday, no discount) so the recursive forecast is complete.
    full_range = pd.date_range(last_date + pd.Timedelta(days=1), future["Date"].max())
    grid = (pd.MultiIndex.from_product([future["Store_id"].unique(), full_range], names=["Store_id", "Date"])
            .to_frame(index=False).merge(stores.reset_index(), on="Store_id"))
    grid = grid.merge(future[["Store_id", "Date", "Holiday", "Discount"]], on=["Store_id", "Date"], how="left")
    grid[["Holiday", "Discount"]] = grid[["Holiday", "Discount"]].fillna(0).astype(int)

    hist = history[history["Store_id"].isin(future["Store_id"]) & (history["Date"] > last_date - pd.Timedelta(days=400))]
    out = model.forecast(hist, grid).merge(future[["Store_id", "Date"]], on=["Store_id", "Date"])
    out = out.sort_values(["Store_id", "Date"])
    predictions = [
        {"store_id": int(r.Store_id), "date": r.Date.strftime("%Y-%m-%d"), "holiday": int(r.Holiday),
         "discount": int(r.Discount), "predicted_sales": round(float(r.Forecast), 2)}
        for r in out.itertuples()
    ]
    return jsonify(predictions=predictions, count=len(predictions),
                   total_predicted_sales=round(float(out["Forecast"].sum()), 2))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
