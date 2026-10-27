"""Render tableau/dashboard_preview.png: a static preview of the Tableau dashboard.

It draws the same views, in the same layout and colours, from the same CSVs as
tableau/Sales_Forecasting_Dashboard.twbx, so the README can show the design
before (and alongside) the live Tableau Public link.

    python scripts/build_tableau.py && python scripts/render_tableau_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "forecasting"))  # style.py only, without the model dependencies
from style import BLUE, GRID, INK, INK_2, ORANGE, SEQUENTIAL  # noqa: E402

OUT = ROOT / "tableau"
NAVY, GREY, BG, CARD, BORDER = "#1F3B73", "#B7C2D0", "#F3F5F9", "#FFFFFF", "#E1E6EF"
W, H = 1300, 2260  # dashboard size in px, as in build_tableau.py

mpl.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.7, "axes.axisbelow": True,
})


def card(fig, x, y, w, h):
    """Card background at pixel box (x, y, w, h), y measured from the top."""
    m = 6
    fig.patches.append(mpl.patches.FancyBboxPatch(
        ((x + m) / W, 1 - (y + h - m) / H), (w - 2 * m) / W, (h - 2 * m) / H,
        boxstyle="round,pad=0,rounding_size=0.004", transform=fig.transFigure,
        facecolor=CARD, edgecolor=BORDER, linewidth=1, zorder=0))


def axes(fig, x, y, w, h, title, subtitle="", top=58, left=70, bottom=40, right=24):
    card(fig, x, y, w, h)
    fig.text((x + 18) / W, 1 - (y + 26) / H, title, fontsize=12, fontweight="bold", color=INK)
    if subtitle:
        fig.text((x + 18) / W, 1 - (y + 45) / H, subtitle, fontsize=9, color=INK_2)
    ax = fig.add_axes([(x + left) / W, 1 - (y + h - bottom) / H,
                       (w - left - right) / W, (h - top - bottom) / H], facecolor=CARD)
    ax.set_zorder(2)  # draw above the card patches
    return ax


def kfmt(v):
    return f"{v / 1000:,.1f}K"


def main() -> None:
    s = pd.read_csv(OUT / "tableau_sales.csv", parse_dates=["Date"])
    models = pd.read_csv(OUT / "tableau_models.csv")
    act = s[s.Series == "Actual"]
    hold = s[s.Period == "Hold-out"]

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
    pad, inner = 16, W - 32
    half = inner / 2

    # Header band
    fig.patches.append(mpl.patches.Rectangle(((pad + 6) / W, 1 - (pad + 114) / H), (inner - 12) / W, 108 / H,
                                             transform=fig.transFigure, facecolor=NAVY, zorder=0))
    fig.text((pad + 26) / W, 1 - (pad + 58) / H, "Product Sales Forecasting", fontsize=24,
             fontweight="bold", color="white")
    fig.text((pad + 26) / W, 1 - (pad + 90) / H, "365 retail stores · 4 formats · 5 location types · "
             "4 regions · daily data Jan 2018 – May 2019 · LightGBM forecast for Jun – Jul 2019",
             fontsize=11, color="#C9D6EA")

    # KPI tiles
    y = pad + 128
    disc = act[act.Discount == "Yes"].Value.mean() / act[act.Discount == "No"].Value.mean() - 1
    holi = act[act.Holiday == "Holiday"].Value.mean() / act[act.Holiday == "Working day"].Value.mean() - 1
    wape = hold.Abs_Error.sum() / hold[hold.Series == "Actual"].Value.sum()
    kpis = [("TOTAL SALES TO DATE", f"{act.Value.sum() / 1e9:,.2f}", " bn"),
            ("DISCOUNT UPLIFT (SALES/DAY)", f"{disc:+.1%}", ""),
            ("HOLIDAY EFFECT (SALES/DAY)", f"{holi:+.1%}", ""),
            ("HOLD-OUT ERROR (WAPE)", f"{wape:.1%}", ""),
            ("JUN – JUL 2019 FORECAST", f"{s[s.Period == 'Future'].Value.sum() / 1e6:,.1f}", " M")]
    kw = inner / 5
    for i, (label, value, unit) in enumerate(kpis):
        x = pad + i * kw
        card(fig, x, y, kw, 120)
        fig.text((x + 18) / W, 1 - (y + 30) / H, label, fontsize=9, fontweight="bold", color=INK_2)
        t = fig.text((x + 18) / W, 1 - (y + 84) / H, value, fontsize=26, fontweight="bold", color=INK)
        fig.canvas.draw()
        bb = t.get_window_extent()
        fig.text(bb.x1 / W + 4 / W, 1 - (y + 82) / H, unit, fontsize=10, color=INK_2)
    y += 128

    # Weekly trend
    ax = axes(fig, pad, y, inner, 420, "Chain sales by week: actuals and 61-day forecast",
              "Orange overlaps blue in Apr–May 2019 (hold-out test), then carries on alone for Jun–Jul 2019")
    for series, color in [("Actual", BLUE), ("Forecast", ORANGE)]:
        # average daily chain sales per week, so partial weeks at the edges don't dip
        daily = s[s.Series == series].groupby("Date").Value.sum() / 1e6
        wk = daily.resample("W-SUN", label="left").mean().dropna()
        ax.plot(wk.index, wk.values, color=color, lw=2, label=series)
    ax.axvspan(pd.Timestamp("2019-04-01"), pd.Timestamp("2019-05-31"), color=GRID, alpha=0.5, lw=0)
    ax.text(pd.Timestamp("2019-04-04"), ax.get_ylim()[0], " hold-out test", fontsize=8, color=INK_2, va="bottom")
    ax.set_ylabel("Avg daily chain sales (M)")
    ax.legend(loc="upper left", frameon=False, fontsize=9, ncols=2)
    y += 428

    # Heatmap: store type x location type
    ax = axes(fig, pad, y, half, 380, "Average daily sales per store: format × location",
              "S4 stores in L2 locations sell the most", left=60, bottom=36)
    pv = act.pivot_table(index="Store_Type", columns="Location_Type", values="Value", aggfunc="mean")
    cmap = mpl.colors.LinearSegmentedColormap.from_list("seq", SEQUENTIAL)
    ax.imshow(pv.values, cmap=cmap, aspect="auto", vmin=np.nanmin(pv.values) * 0.8)
    for (i, j), v in np.ndenumerate(pv.values):
        if not np.isnan(v):
            ax.text(j, i, kfmt(v), ha="center", va="center", fontsize=10,
                    color="white" if v > 45000 else INK)
    ax.set_xticks(range(pv.shape[1]), pv.columns)
    ax.set_yticks(range(pv.shape[0]), pv.index)
    ax.grid(False)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

    # Discount by store type
    ax = axes(fig, pad + half, y, half, 380, "Discounts lift sales in every store type",
              "Average daily sales per store, discount vs no discount", left=60)
    g = act.groupby(["Store_Type", "Discount"]).Value.mean().unstack()
    ys = np.arange(len(g))
    for k, (flag, color) in enumerate([("No", GREY), ("Yes", BLUE)]):
        bars = ax.barh(ys + (k - 0.5) * 0.38, g[flag], height=0.34, color=color, label=f"Discount: {flag}")
        ax.bar_label(bars, [kfmt(v) for v in g[flag]], padding=4, fontsize=8.5, color=INK_2)
    ax.set_yticks(ys, g.index)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}K"))
    ax.set_xlim(0, g.values.max() * 1.18)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    y += 388

    # Weekday
    ax = axes(fig, pad, y, half, 330, "Weekends are the peak", "Average daily sales per store by weekday")
    order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    wd = act.groupby(act.Date.dt.day_name()).Value.mean().reindex(order)
    bars = ax.bar([d[:3] for d in order], wd.values, color=BLUE, width=0.62)
    ax.bar_label(bars, [kfmt(v) for v in wd.values], padding=3, fontsize=8.5, color=INK_2)
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}K"))
    ax.set_ylim(0, wd.max() * 1.12)
    ax.grid(axis="x", visible=False)

    # Region
    ax = axes(fig, pad + half, y, half, 330, "Region matters little", "Average daily sales per store", left=50)
    rg = act.groupby("Region_Code").Value.mean()
    bars = ax.barh(rg.index, rg.values, color=BLUE, height=0.55)
    ax.bar_label(bars, [kfmt(v) for v in rg.values], padding=4, fontsize=8.5, color=INK_2)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, rg.max() * 1.15)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}K"))
    y += 338

    # Hold-out scatter
    ax = axes(fig, pad, y, half, 400, "Hold-out test: actual vs forecast per store",
              "Each dot is one store's Apr–May 2019 total; on the diagonal = perfect", left=64)
    st = hold.pivot_table(index="Store_id", columns="Series", values="Value", aggfunc="sum") / 1e6
    lim = [0, st.values.max() * 1.05]
    ax.plot(lim, lim, color=INK_2, lw=1, ls="--")
    ax.scatter(st.Actual, st.Forecast, s=34, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.8)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Actual sales (M)")
    ax.set_ylabel("Forecast (M)")

    # WAPE by store type
    ax = axes(fig, pad + half, y, half, 400, "Forecast error by store type", "Hold-out WAPE, store × day", left=50)
    hf = hold[hold.Series == "Forecast"].groupby("Store_Type").Abs_Error.sum()
    ha = hold[hold.Series == "Actual"].groupby("Store_Type").Value.sum()
    wt = (hf / ha).sort_index()
    bars = ax.barh(wt.index, wt.values, color=BLUE, height=0.55)
    ax.bar_label(bars, [f"{v:.1%}" for v in wt.values], padding=4, fontsize=9, color=INK_2)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, wt.max() * 1.2)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    y += 408

    # Model leaderboard
    ax = axes(fig, pad, y, inner, 330, "10 models, 3-fold time-series cross-validation",
              "WAPE, lower is better", left=370)
    colors = [ORANGE if f == "Final model" else GREY for f in models.Final]
    bars = ax.barh(models.Model, models.WAPE, color=colors, height=0.62)
    ax.bar_label(bars, [f"{v:.1%}" for v in models.WAPE], padding=4, fontsize=8.5, color=INK_2)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, models.WAPE.max() * 1.12)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    ax.tick_params(axis="y", labelsize=9)
    y += 338

    fig.text((pad + 18) / W, 1 - (y + 26) / H,
             "Final model: global LightGBM on log sales with 61-day-shifted lags (no order leakage). Cross-validated "
             "WAPE 15.3% vs 22.8% for a seasonal naive baseline.\nHold-out Apr–May 2019: store-day WAPE 16.8%, "
             "store-total WAPE 10.5%. WAPE = sum of absolute errors ÷ sum of sales. "
             "Code, notebook and app: github.com/dot-hpg/sales-forecasting",
             fontsize=9, color=INK_2, va="top", linespacing=1.5)

    fig.savefig(OUT / "dashboard_preview.png", dpi=150, facecolor=BG)
    print(OUT / "dashboard_preview.png")


if __name__ == "__main__":
    main()
