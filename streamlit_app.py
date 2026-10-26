"""Product Sales Forecasting: mobile-friendly Streamlit app.

Run locally:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forecasting import SalesForecaster
from forecasting.config import HISTORY_FILE, METADATA_FILE, MODEL_FILE, PROCESSED_DIR, TEST_FILE
from forecasting.features import load_raw
from forecasting.style import BLUE, GRID, INK, INK_2, MUTED, ORANGE, SEQUENTIAL, SERIES

st.set_page_config(page_title="Sales Forecasting", page_icon="📈", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 900px;}
[data-testid="stMetricValue"] {font-size: 1.45rem;}
[data-testid="stMetricLabel"] p {font-size: .85rem;}
.small-note {color: #6b6a66; font-size: .85rem;}
.stTabs [data-baseweb="tab-list"] {gap: .25rem; flex-wrap: wrap;}
.stTabs [data-baseweb="tab"] {padding: .4rem .7rem;}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem;}
  h1 {font-size: 1.6rem !important;}
  [data-testid="stMetricValue"] {font-size: 1.2rem;}
}
</style>
""", unsafe_allow_html=True)

PLOT_CONFIG = {"displayModeBar": False, "responsive": True}


# ----------------------------------------------------------------- loading
@st.cache_resource(show_spinner="Loading model...")
def load_model() -> SalesForecaster:
    return SalesForecaster.load(MODEL_FILE)


@st.cache_data(show_spinner=False)
def load_data():
    history = pd.read_parquet(HISTORY_FILE)
    history["Date"] = pd.to_datetime(history["Date"])
    plan = load_raw(TEST_FILE)
    test_fc = pd.read_csv(PROCESSED_DIR / "test_forecast.csv", parse_dates=["Date"])
    meta = json.loads(METADATA_FILE.read_text())
    return history, plan, test_fc, meta


model = load_model()
history, plan, test_fc, meta = load_data()
stores = history.drop_duplicates("Store_id").set_index("Store_id")[["Store_Type", "Location_Type", "Region_Code"]]
last_date = history["Date"].max()
holiday_calendar = plan.drop_duplicates("Date").set_index("Date")["Holiday"]


def fmt_money(v: float) -> str:
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:,.1f}K"
    return f"{v:,.0f}"


def base_layout(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=30, b=8), hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=11)),
        font=dict(size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickformat="~s")
    return fig


@st.cache_data(show_spinner=False, max_entries=64)
def forecast_store(store_id: int, horizon: int, discount_mode: str, extra_holidays: tuple) -> pd.DataFrame:
    dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
    attrs = stores.loc[store_id]
    fut = pd.DataFrame({"Store_id": store_id, "Store_Type": attrs.Store_Type, "Location_Type": attrs.Location_Type,
                        "Region_Code": attrs.Region_Code, "Date": dates})
    fut["Holiday"] = fut["Date"].map(holiday_calendar).fillna(0).astype(int)
    fut.loc[fut["Date"].isin(pd.to_datetime(list(extra_holidays))), "Holiday"] = 1
    planned = plan[plan.Store_id == store_id].set_index("Date")["Discount"]
    if discount_mode == "Company plan":
        fut["Discount"] = fut["Date"].map(planned).fillna(0).astype(int)
    elif discount_mode == "Every day":
        fut["Discount"] = 1
    elif discount_mode == "Weekends only":
        fut["Discount"] = (fut["Date"].dt.dayofweek >= 5).astype(int)
    else:
        fut["Discount"] = 0
    hist = history[(history.Store_id == store_id) & (history.Date > last_date - pd.Timedelta(days=400))]
    return model.forecast(hist, fut)


# ------------------------------------------------------------------- header
st.title("📈 Product Sales Forecasting")
st.markdown(
    f"<span class='small-note'>Daily sales forecasts for 365 stores · LightGBM trained on "
    f"{meta['trained_on'].replace(' to ', ' → ')} · history ends {last_date:%d %b %Y}</span>",
    unsafe_allow_html=True)

tab_store, tab_chain, tab_insights, tab_model = st.tabs(["🏬 Store forecast", "🌐 Chain view", "💡 Insights", "🧠 Model"])

# ============================================================ store forecast
with tab_store:
    labels = {sid: f"Store {sid} · {r.Store_Type} · {r.Location_Type} · {r.Region_Code}" for sid, r in stores.iterrows()}
    store_id = st.selectbox("Store", options=list(labels), format_func=labels.get, index=0)
    c1, c2 = st.columns(2)
    horizon = c1.select_slider("Forecast days", options=[7, 14, 30, 61, 90, 120], value=61)
    discount_mode = c2.selectbox("Discount plan", ["Company plan", "No discount", "Weekends only", "Every day"],
                                 help="'Company plan' uses the discount calendar in TEST_FINAL.csv (June-July 2019); "
                                      "days after July 2019 have no planned discount.")
    horizon_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon)
    with st.expander("Holidays in this period"):
        known = [d.date() for d in horizon_dates if holiday_calendar.get(d, 0) == 1]
        st.caption("Known public holidays are included automatically: "
                   + (", ".join(f"{d:%d %b}" for d in known) if known else "none in this window") + ".")
        extra = st.multiselect("Add extra holidays", options=[d.date() for d in horizon_dates],
                               format_func=lambda d: f"{d:%a %d %b %Y}")

    with st.spinner("Forecasting..."):
        fc = forecast_store(store_id, horizon, discount_mode, tuple(str(d) for d in extra))
        baseline = forecast_store(store_id, horizon, "No discount", tuple(str(d) for d in extra))

    total = fc["Forecast"].sum()
    ly = history[(history.Store_id == store_id)
                 & history.Date.between(horizon_dates[0] - pd.DateOffset(years=1), horizon_dates[-1] - pd.DateOffset(years=1))]
    uplift = total - baseline["Forecast"].sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Forecast total", fmt_money(total))
    m2.metric("Avg per day", fmt_money(fc["Forecast"].mean()))
    if len(ly) == horizon:
        m3.metric("Same days 2018", fmt_money(ly["Sales"].sum()), f"{total / ly['Sales'].sum() - 1:+.1%}", delta_color="off",
                  help="Actual sales in the same calendar window one year earlier; the change is the forecast compared with it.")
    else:
        m3.metric("Discount days", f"{int(fc['Discount'].sum())}")
    if discount_mode != "No discount":
        st.info(f"The discount plan adds an estimated **{fmt_money(uplift)}** "
                f"(**{uplift / baseline['Forecast'].sum():+.1%}**) compared with running no discounts.")

    recent = history[(history.Store_id == store_id) & (history.Date > last_date - pd.Timedelta(days=90))]
    fig = go.Figure()
    fig.add_scatter(x=recent.Date, y=recent.Sales, name="Actual", line=dict(color=INK, width=1.6))
    if discount_mode != "No discount":
        fig.add_scatter(x=baseline.Date, y=baseline.Forecast, name="No-discount scenario",
                        line=dict(color=MUTED, width=1.4, dash="dot"))
    fig.add_scatter(x=fc.Date, y=fc.Forecast, name="Forecast", line=dict(color=BLUE, width=2.2))
    disc_days = fc[fc.Discount == 1]
    fig.add_scatter(x=disc_days.Date, y=disc_days.Forecast, mode="markers", name="Discount day",
                    marker=dict(color=ORANGE, size=6, line=dict(color="white", width=1)), hoverinfo="skip")
    hol_days = fc[fc.Holiday == 1]
    for d in hol_days.Date:
        fig.add_vline(x=d, line=dict(color=GRID, width=6), layer="below")
    st.plotly_chart(base_layout(fig, 360), width="stretch", config=PLOT_CONFIG)
    st.caption("Grey bands mark holidays. Orange dots mark discount days.")

    table = fc[["Date", "Holiday", "Discount", "Forecast"]].assign(
        Day=lambda d: d.Date.dt.strftime("%a"), Date=lambda d: d.Date.dt.date,
        Holiday=lambda d: d.Holiday.map({1: "Yes", 0: ""}), Discount=lambda d: d.Discount.map({1: "Yes", 0: ""}),
        Forecast=lambda d: d.Forecast.round(0))[["Date", "Day", "Holiday", "Discount", "Forecast"]]
    with st.expander("Daily forecast table"):
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Forecast": st.column_config.NumberColumn(format="%.0f")})
    st.download_button("⬇️ Download forecast (CSV)", table.to_csv(index=False).encode(),
                       file_name=f"store_{store_id}_forecast.csv", mime="text/csv", width="stretch")

# ================================================================= chain view
with tab_chain:
    st.markdown("Forecast for **June and July 2019** across the chain, using the company's holiday and discount plan.")
    f1, f2, f3 = st.columns(3)
    pick = lambda col, box: box.multiselect(col.replace("_", " "), sorted(stores[col].unique()), placeholder="All")
    sel_type, sel_loc, sel_reg = pick("Store_Type", f1), pick("Location_Type", f2), pick("Region_Code", f3)
    mask = pd.Series(True, index=test_fc.index)
    for col, sel in [("Store_Type", sel_type), ("Location_Type", sel_loc), ("Region_Code", sel_reg)]:
        if sel:
            mask &= test_fc[col].isin(sel)
    sub = test_fc[mask]
    hist_mask = history.Store_id.isin(sub.Store_id.unique())
    n_stores = sub.Store_id.nunique()

    if n_stores == 0:
        st.warning("No stores match these filters.")
    else:
        ly = history[hist_mask & history.Date.between("2018-06-01", "2018-07-31")].Sales.sum()
        k1, k2, k3 = st.columns(3)
        k1.metric("Stores", n_stores)
        k2.metric("Forecast Jun-Jul", fmt_money(sub.Forecast.sum()))
        k3.metric("Jun-Jul 2018 actual", fmt_money(ly), f"{sub.Forecast.sum() / ly - 1:+.1%}", delta_color="off",
                  help="The change shows the forecast compared with the same two months of 2018.")

        actual_daily = history[hist_mask & (history.Date >= "2019-03-01")].groupby("Date").Sales.sum()
        fc_daily = sub.groupby("Date").Forecast.sum()
        fig = go.Figure()
        fig.add_scatter(x=actual_daily.index, y=actual_daily.values, name="Actual", line=dict(color=INK, width=1.6))
        fig.add_scatter(x=fc_daily.index, y=fc_daily.values, name="Forecast", line=dict(color=BLUE, width=2.2))
        st.plotly_chart(base_layout(fig), width="stretch", config=PLOT_CONFIG)

        by = st.radio("Break down by", ["Store_Type", "Location_Type", "Region_Code"], horizontal=True,
                      format_func=lambda c: c.replace("_", " "))
        seg = sub.groupby(by).Forecast.sum().sort_index()
        fig = go.Figure(go.Bar(x=seg.index, y=seg.values, marker_color=BLUE,
                               text=[fmt_money(v) for v in seg.values], textposition="outside"))
        fig.update_traces(marker_line_width=0, width=0.55, cliponaxis=False)
        st.plotly_chart(base_layout(fig, 300), width="stretch", config=PLOT_CONFIG)

        top = (sub.groupby("Store_id").Forecast.sum().sort_values(ascending=False).head(10).rename("Forecast Jun-Jul")
               .to_frame().join(stores).reset_index())
        st.markdown("**Top 10 stores by forecast**")
        st.dataframe(top, hide_index=True, width="stretch",
                     column_config={"Forecast Jun-Jul": st.column_config.NumberColumn(format="%.0f")})
        st.download_button("⬇️ Download chain forecast (CSV)", sub.to_csv(index=False).encode(),
                           file_name="chain_forecast_jun_jul_2019.csv", mime="text/csv", width="stretch")

# =================================================================== insights
with tab_insights:
    h = history[history.Sales > 0]
    disc = h.groupby("Discount").Sales.mean()
    hol = h.groupby("Holiday").Sales.mean()
    wk = h.groupby(h.Date.dt.dayofweek >= 5).Sales.mean()
    i1, i2, i3 = st.columns(3)
    i1.metric("Discount day uplift", f"{disc[1] / disc[0] - 1:+.0%}")
    i2.metric("Holiday effect", f"{hol[1] / hol[0] - 1:+.0%}")
    i3.metric("Weekend vs weekday", f"{wk[True] / wk[False] - 1:+.0%}")

    st.markdown("**Average daily sales per store, by segment**")
    seg_col = st.radio("Segment", ["Store_Type", "Location_Type", "Region_Code"], horizontal=True,
                       format_func=lambda c: c.replace("_", " "), key="ins_seg")
    s = h.groupby([seg_col, "Discount"]).Sales.mean().unstack()
    fig = go.Figure()
    fig.add_bar(x=s.index, y=s[0], name="No discount", marker_color=SEQUENTIAL[1])
    fig.add_bar(x=s.index, y=s[1], name="Discount", marker_color=BLUE)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    st.plotly_chart(base_layout(fig, 300), width="stretch", config=PLOT_CONFIG)

    dow = h.groupby(h.Date.dt.dayofweek).Sales.mean()
    fig = go.Figure(go.Bar(x=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], y=dow.values,
                           marker_color=[SEQUENTIAL[1]] * 5 + [BLUE] * 2))
    fig.update_layout(title=dict(text="Average daily sales by weekday", font=dict(size=13)))
    st.plotly_chart(base_layout(fig, 260), width="stretch", config=PLOT_CONFIG)

    st.markdown("""
**What the data says**
- **Discounts work everywhere.** Every one of the 365 stores sells more on discount days. Discounts run as chain-wide campaigns.
- **Holidays reduce sales.** Stores sell noticeably less on public holidays, so stock and staff should be cut back, not increased.
- **Weekends are the busiest days.** Saturday and Sunday are the strongest days of the week.
- **Format and location matter most.** S4 and S3 stores and L2 locations have the highest daily sales; region matters much less.
- **Orders track sales closely** (correlation 0.94), but orders are only known after the day, so the forecast does not use them.
""")

# ====================================================================== model
with tab_model:
    sd, cd = meta["holdout_store_day"], meta["holdout_chain_day"]
    st.markdown(f"**Hold-out test:** trained up to 31 Mar 2019, forecast {meta['holdout_period'].replace(' to ', ' → ')} "
                "(61 days, the same length as the real forecast).")
    a1, a2, a3 = st.columns(3)
    a1.metric("WAPE, store-day", f"{sd['WAPE_%']:.1f}%")
    a2.metric("WAPE, chain-day", f"{cd['WAPE_%']:.1f}%")
    a3.metric("R², store-day", f"{sd['R2']:.2f}")
    imp = pd.Series(meta["feature_importance_gain_pct"]).sort_values().tail(12)
    fig = go.Figure(go.Bar(x=imp.values, y=imp.index, orientation="h", marker_color=BLUE))
    fig.update_layout(title=dict(text="What drives the forecast (share of model gain, %)", font=dict(size=13)), hovermode="y")
    fig.update_xaxes(gridcolor=GRID, tickformat=".0f"); fig.update_yaxes(showgrid=False)
    st.plotly_chart(base_layout(fig, 380).update_layout(hovermode="y"), width="stretch", config=PLOT_CONFIG)
    st.markdown("""
**How it works**
1. One **LightGBM** model is trained on all 365 stores at once, on log-sales, so it learns patterns shared by stores
   and each store's own level.
2. It uses only what is known in advance: the calendar, holidays, the discount plan, store attributes and each store's
   sales level from **at least 61 days earlier**. Order counts are excluded because they would leak the answer.
3. For horizons longer than 61 days it forecasts in 61-day blocks and feeds its own forecasts back in.
4. It was chosen over linear regression, random forest, XGBoost, SARIMAX, Holt-Winters and Prophet using rolling-origin
   cross-validation. Full details are in the notebook on GitHub.
""")
    st.markdown("[📓 Notebook and code on GitHub](https://github.com/dot-hpg/sales-forecasting)")
