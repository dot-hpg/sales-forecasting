"""Data loading and feature engineering shared by the notebook, the app and the API.

Every feature here is something a planner knows on the day the forecast is made:
the calendar, the holiday calendar, the discount plan, each store's attributes and
sales from at least ``HORIZON`` days earlier. ``#Order`` is deliberately left out
because it is only known after the day is over (it is a 0.94-correlated proxy of
the target, so using it would leak the answer into the forecast).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    CATEGORICAL, EXTRA_LAGS, HORIZON, ROLLING_WINDOWS, SAME_WEEKDAY_LAGS,
    TEST_FILE, TRAIN_FILE,
)


def load_raw(path=TRAIN_FILE) -> pd.DataFrame:
    """Read a raw CSV and give it clean column names and types."""
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.rename(columns={"#Order": "Orders"})
    df["Discount"] = (df["Discount"].astype(str).str.lower() == "yes").astype(int)
    df["Holiday"] = df["Holiday"].astype(int)
    for col in CATEGORICAL:
        df[col] = df[col].astype(str)
    return df.sort_values(["Store_id", "Date"]).reset_index(drop=True)


def load_train_test() -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_raw(TRAIN_FILE), load_raw(TEST_FILE)


def store_master(df: pd.DataFrame) -> pd.DataFrame:
    """One row per store with its static attributes."""
    return (df[["Store_id", *CATEGORICAL]].drop_duplicates("Store_id")
            .sort_values("Store_id").reset_index(drop=True))


# --------------------------------------------------------------------------- #
# Feature blocks
# --------------------------------------------------------------------------- #
def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    d = df["Date"]
    df["dayofweek"] = d.dt.dayofweek
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)
    df["day"] = d.dt.day
    df["month"] = d.dt.month
    df["weekofyear"] = d.dt.isocalendar().week.astype(int)
    df["dayofyear"] = d.dt.dayofyear
    df["is_month_start"] = (df["day"] <= 3).astype(int)
    df["is_month_end"] = d.dt.is_month_end.astype(int) | (d.dt.days_in_month - df["day"] < 3)
    df["is_month_end"] = df["is_month_end"].astype(int)
    return df


def _days_between(dates: pd.Series, flags: pd.Series, direction: str, cap: int = 15) -> pd.Series:
    """Days since the last / until the next flagged date, capped."""
    cal = pd.DataFrame({"Date": dates, "flag": flags}).drop_duplicates("Date").sort_values("Date")
    event = cal["Date"].where(cal["flag"] == 1)
    if direction == "since":
        ref = event.ffill()
        out = (cal["Date"] - ref).dt.days
    else:
        ref = event.bfill()
        out = (ref - cal["Date"]).dt.days
    out = out.fillna(cap).clip(upper=cap)
    return dates.map(dict(zip(cal["Date"], out)))


def add_event_features(df: pd.DataFrame) -> pd.DataFrame:
    """Holiday proximity and discount-campaign context."""
    df = df.sort_values(["Store_id", "Date"])
    df["days_since_holiday"] = _days_between(df["Date"], df["Holiday"], "since")
    df["days_to_holiday"] = _days_between(df["Date"], df["Holiday"], "until")
    g = df.groupby("Store_id")
    df["holiday_prev_day"] = g["Holiday"].shift(1).fillna(0).astype(int)
    df["holiday_next_day"] = g["Holiday"].shift(-1).fillna(0).astype(int)
    df["discount_prev_day"] = g["Discount"].shift(1).fillna(0).astype(int)
    df["discount_next_day"] = g["Discount"].shift(-1).fillna(0).astype(int)
    # Discounts run as chain-wide campaigns: share of stores on discount that day.
    df["discount_share_day"] = df.groupby("Date")["Discount"].transform("mean")
    # Consecutive days the store has been on discount (campaign fatigue).
    run_id = (df["Discount"] != g["Discount"].shift(1)).cumsum()
    df["discount_streak"] = df.groupby(run_id).cumcount().add(1).where(df["Discount"] == 1, 0)
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lags and rolling statistics of log-sales, all at least HORIZON days old."""
    df = df.sort_values(["Store_id", "Date"])
    # Zero sales are store closures, not demand, so they are masked out of the lags.
    log_sales = np.log1p(df["Sales"].where(df["Sales"] > 0))
    g = log_sales.groupby(df["Store_id"])
    for lag in SAME_WEEKDAY_LAGS + EXTRA_LAGS:
        df[f"lag_{lag}"] = g.shift(lag)
    df["same_weekday_mean"] = df[[f"lag_{l}" for l in SAME_WEEKDAY_LAGS]].mean(axis=1)
    shifted = g.shift(HORIZON)
    gs = shifted.groupby(df["Store_id"])
    for w in ROLLING_WINDOWS:
        df[f"roll_mean_{w}"] = gs.transform(lambda s, w=w: s.rolling(w, min_periods=max(2, w // 2)).mean())
    df["roll_std_28"] = gs.transform(lambda s: s.rolling(28, min_periods=14).std())
    df["trend_28_91"] = df["roll_mean_28"] - df["roll_mean_91"]
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full feature matrix for a store x date panel (history and/or future rows).

    ``df`` must contain Store_id, Date, Holiday, Discount, the store attributes and
    a Sales column (NaN for days still to be forecast).
    """
    df = df.copy()
    if "Sales" not in df:
        df["Sales"] = np.nan
    df = add_calendar(df)
    df = add_event_features(df)
    df = add_lag_features(df)
    for col in CATEGORICAL:
        df[col] = pd.Categorical(df[col], categories=CATEGORY_LEVELS[col])
    df["store"] = pd.Categorical(df["Store_id"], categories=STORE_IDS)
    return df


STORE_IDS = list(range(1, 366))
CATEGORY_LEVELS = {
    "Store_Type": ["S1", "S2", "S3", "S4"],
    "Location_Type": ["L1", "L2", "L3", "L4", "L5"],
    "Region_Code": ["R1", "R2", "R3", "R4"],
}

# Final feature set, chosen with rolling-origin cross-validation (see the notebook):
# point lags were noisy and hurt accuracy, while smoothed store levels (rolling
# means) and a store identity feature helped.
FEATURES = [
    "Holiday", "Discount", "store", *CATEGORICAL,
    "dayofweek", "is_weekend", "month", "is_month_start", "is_month_end",
    "days_since_holiday", "days_to_holiday", "holiday_prev_day", "holiday_next_day",
    "discount_prev_day", "discount_next_day", "discount_share_day", "discount_streak",
    *[f"roll_mean_{w}" for w in ROLLING_WINDOWS],
]

# Extra features evaluated in the notebook's ablation study but not used in the final model.
ABLATION_FEATURES = (
    ["day", "dayofyear", "weekofyear", "same_weekday_mean", "roll_std_28", "trend_28_91"]
    + [f"lag_{l}" for l in SAME_WEEKDAY_LAGS + EXTRA_LAGS]
)
