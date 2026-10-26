import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forecasting import FEATURES, SalesForecaster, build_features, evaluate  # noqa: E402
from forecasting.config import HISTORY_FILE, HORIZON  # noqa: E402


def _panel(days=200, stores=3):
    dates = pd.date_range("2018-01-01", periods=days)
    rows = [{"Store_id": s, "Store_Type": "S1", "Location_Type": "L1", "Region_Code": "R1", "Date": d,
             "Holiday": int(d.day == 1), "Discount": int(d.dayofweek >= 5), "Sales": 1000.0 + s + d.dayofweek}
            for s in range(1, stores + 1) for d in dates]
    return pd.DataFrame(rows)


def test_features_present_and_no_target_leak():
    feat = build_features(_panel())
    assert set(FEATURES) <= set(feat.columns)
    # Rolling store levels must only use sales at least HORIZON days old.
    first_store = feat[feat.Store_id == 1].reset_index(drop=True)
    assert first_store.loc[:HORIZON - 1, "roll_mean_7"].isna().all()


def test_future_rows_do_not_change_history_features():
    panel = _panel()
    hist_only = build_features(panel)
    future = panel[panel.Date == panel.Date.max()].assign(Date=lambda d: d.Date + pd.Timedelta(days=1), Sales=np.nan)
    both = build_features(pd.concat([panel, future]))
    cols = [f for f in FEATURES if f.startswith("roll_mean")]
    a = hist_only.sort_values(["Store_id", "Date"])[cols].reset_index(drop=True)
    b = both[both.Sales.notna()].sort_values(["Store_id", "Date"])[cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_metrics():
    r = evaluate([100, 200], [110, 190])
    assert np.isclose(r["MAE"], 10) and np.isclose(r["WAPE_%"], 20 / 300 * 100)


def test_saved_model_forecasts_whole_horizon():
    model = SalesForecaster.load()
    hist = pd.read_parquet(HISTORY_FILE)
    hist["Date"] = pd.to_datetime(hist["Date"])
    store = hist[hist.Store_id == 5]
    fut = store.tail(1)[["Store_id", "Store_Type", "Location_Type", "Region_Code"]].merge(
        pd.DataFrame({"Date": pd.date_range("2019-06-01", periods=130)}), how="cross").assign(Holiday=0, Discount=0)
    out = model.forecast(store, fut)
    assert len(out) == 130 and out.Forecast.notna().all() and (out.Forecast > 0).all()
