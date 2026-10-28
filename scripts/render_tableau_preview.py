"""Render tableau/dashboard_preview.png: a static preview of the Tableau dashboard.

It follows the dashboard plan in build_tableau.py (same rows, widths, titles and
colours) and draws each view from the same CSVs, so the README can show the
design before (and alongside) the live Tableau Public link.

    python scripts/build_tableau.py && python scripts/render_tableau_preview.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import squarify

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "forecasting"))  # style.py only, without the model dependencies
sys.path.insert(0, str(ROOT / "scripts"))
from style import GRID, INK_2, SEQUENTIAL  # noqa: E402
import build_tableau as tb  # noqa: E402

OUT = ROOT / "tableau"
W, H, PAD, GAP = tb.W, tb.H, tb.PAD, tb.GAP
NAVY, BLUE, ORANGE, GREY, INK, MUTED, BG = tb.NAVY, tb.BLUE, tb.ORANGE, tb.GREY, tb.INK, tb.MUTED, tb.BG
CARD, BORDER = "#FFFFFF", "#E1E6EF"
SEQ = mpl.colors.LinearSegmentedColormap.from_list("seq", SEQUENTIAL)

mpl.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False, "axes.axisbelow": True,
})
K = mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}K")
PCT = mpl.ticker.PercentFormatter(1, decimals=0)


def fx(x):
    return x / W


def fy(y):
    return 1 - y / H


def box(fig, x, y, w, h, color, edge=None, m=5):
    fig.patches.append(mpl.patches.FancyBboxPatch(
        (fx(x + m), fy(y + h - m)), (w - 2 * m) / W, (h - 2 * m) / H, boxstyle="round,pad=0,rounding_size=0.002",
        transform=fig.transFigure, facecolor=color, edgecolor=edge or color, linewidth=1, zorder=0))


def runs_text(fig, x, y, runs_xml, color_default=INK):
    """Draw Tableau formatted-text runs (title + optional second line) at pixel (x, y)."""
    parts = re.findall(r"<run([^>]*)>(.*?)</run>", runs_xml)
    lines, cur = [], []
    for attrs, text in parts:
        if text.startswith("Æ"):
            lines.append(cur)
            cur = []
            continue
        size = float(re.search(r"fontsize='(\d+)'", attrs).group(1)) if "fontsize" in attrs else 10
        color = re.search(r"fontcolor='([^']+)'", attrs).group(1) if "fontcolor" in attrs else color_default
        cur.append((html.unescape(text), size, color, "bold" if "bold='true'" in attrs else "normal"))
    lines.append(cur)
    for line in lines:
        cx = x
        lh = max(s for _, s, _, _ in line) if line else 10
        for text, size, color, weight in line:
            t = fig.text(fx(cx), fy(y + lh * 1.25), text, fontsize=size * 0.95, color=color, fontweight=weight)
            fig.canvas.draw()
            cx = t.get_window_extent().x1 * W / fig.bbox.width + 1
        y += lh * 1.9


def view(fig, x, y, w, h, title, subtitle, left=60, bottom=34, right=18, top=60):
    box(fig, x, y, w, h, CARD, BORDER)
    fig.text(fx(x + 16), fy(y + 26), title, fontsize=11.5, fontweight="bold", color=INK)
    if subtitle:
        fig.text(fx(x + 16), fy(y + 44), subtitle, fontsize=8.3, color=MUTED)
    ax = fig.add_axes([fx(x + left), fy(y + h - bottom), (w - left - right) / W, (h - top - bottom) / H],
                      facecolor=CARD)
    ax.set_zorder(2)
    return ax


def kfmt(v):
    return f"{v / 1000:,.1f}K"


def main() -> None:
    s = pd.read_csv(OUT / "tableau_sales.csv", parse_dates=["Date"])
    models = pd.read_csv(OUT / "tableau_models.csv")
    act = s[s.Series == "Actual"]
    hold = s[s.Period == "Hold-out"]
    titles = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(
        r"<worksheet name='([^']+)'>.*?<run[^>]*>([^<]*)</run>(?:<run>Æ&#10;</run><run[^>]*>([^<]*)</run>)?",
        tb.build_workbook(), flags=re.S)}
    titles = {k: (html.unescape(v[0]), html.unescape(v[1] or "")) for k, v in titles.items()}

    disc = act[act.Discount == "Yes"].Value.mean() / act[act.Discount == "No"].Value.mean() - 1
    holi = act[act.Holiday == "Holiday"].Value.mean() / act[act.Holiday == "Working day"].Value.mean() - 1
    wape = hold.Abs_Error.sum() / hold[hold.Series == "Actual"].Value.sum()
    kpi_values = {"KPI Total Sales": (f"{act.Value.sum() / 1e9:,.2f}", " bn"),
                  "KPI Avg Store Day": (f"{act.Value.mean():,.0f}", ""),
                  "KPI Discount Uplift": (f"{disc:.1%}", " per day"),
                  "KPI Holiday Effect": (f"{holi:.1%}", " per day"),
                  "KPI Hold-out WAPE": (f"{wape:.1%}", " store-day"),
                  "KPI Forecast": (f"{s[s.Period == 'Future'].Value.sum() / 1e6:,.1f}", " M")}

    def draw(name, x, y, w, h):
        title, sub = titles[name]
        if name.startswith("KPI"):
            box(fig, x, y, w, h, CARD, BORDER)
            fig.text(fx(x + 16), fy(y + 30), title, fontsize=8.3, fontweight="bold", color=MUTED)
            value, unit = kpi_values[name]
            t = fig.text(fx(x + 16), fy(y + 84), value, fontsize=25, fontweight="bold", color=INK)
            fig.canvas.draw()
            fig.text(t.get_window_extent().x1 / fig.bbox.width + fx(4), fy(y + 82), unit, fontsize=10, color=MUTED)
        elif name == "Sales Trend":
            ax = view(fig, x, y, w, h, title, sub, left=56)
            for series, color in [("Actual", BLUE), ("Forecast", ORANGE)]:
                daily = s[s.Series == series].groupby("Date").Value.sum()
                wk = daily.resample("W-SUN", label="left").mean().dropna()
                ax.plot(wk.index, wk.values, color=color, lw=2, label=series)
            ax.axvspan(pd.Timestamp("2019-04-01"), pd.Timestamp("2019-05-31"), color=GRID, alpha=0.6, lw=0)
            ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.0f}M"))
            ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%b %y"))
            ax.legend(loc="upper left", frameon=False, fontsize=8.5, ncols=2)
        elif name == "Sales Treemap":
            ax = view(fig, x, y, w, h, title, sub, left=16, bottom=16, right=16)
            g = act.groupby(["Store_Type", "Location_Type"]).Value.agg(["sum", "mean"]).sort_values("sum",
                                                                                                   ascending=False)
            rects = squarify.squarify(squarify.normalize_sizes(g["sum"].values, 100, 100), 0, 0, 100, 100)
            norm = mpl.colors.Normalize(g["mean"].min() * 0.75, g["mean"].max())
            for (idx, row), r in zip(g.iterrows(), rects):
                ax.add_patch(mpl.patches.Rectangle((r["x"], r["y"]), r["dx"], r["dy"], facecolor=SEQ(norm(row["mean"])),
                                                   edgecolor="white", linewidth=2))
                if r["dx"] > 12 and r["dy"] > 9:
                    ax.text(r["x"] + 1.5, r["y"] + r["dy"] - 2, f"{idx[0]} · {idx[1]}\n{row['sum'] / 1e9:.2f} bn",
                            va="top", fontsize=8, color="white", fontweight="bold")
            ax.set_xlim(0, 100)
            ax.set_ylim(0, 100)
            ax.axis("off")
        elif name == "Seasonality Heatmap":
            ax = view(fig, x, y, w, h, title, sub, left=50, bottom=30)
            d = act.groupby("Date").Value.sum()
            m = d.groupby([d.index.year, d.index.month]).mean().unstack() / 1e6
            ax.imshow(m.values, cmap=SEQ, aspect="auto", vmin=np.nanmin(m.values) * 0.85)
            for (i, j), v in np.ndenumerate(m.values):
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=9,
                            color="white" if v > np.nanmean(m.values) else INK)
            ax.set_xticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                                      "Dec"])
            ax.set_yticks(range(len(m)), m.index)
            ax.tick_params(length=0)
            for sp in ax.spines.values():
                sp.set_visible(False)
        elif name == "Weekday Pattern":
            ax = view(fig, x, y, w, h, title, sub, left=50)
            order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            wd = act.groupby(act.Date.dt.day_name()).Value.mean().reindex(order)
            colors = [BLUE if d in ("Saturday", "Sunday") else GREY for d in order]
            bars = ax.bar([d[:3] for d in order], wd.values, color=colors, width=0.62)
            ax.bar_label(bars, [kfmt(v) for v in wd.values], padding=3, fontsize=8, color=INK_2)
            ax.yaxis.set_major_formatter(K)
            ax.set_ylim(0, wd.max() * 1.15)
        elif name == "Store Type x Location":
            ax = view(fig, x, y, w, h, title, sub, left=44, bottom=30)
            pv = act.pivot_table(index="Store_Type", columns="Location_Type", values="Value", aggfunc="mean")
            ax.imshow(pv.values, cmap=SEQ, aspect="auto", vmin=np.nanmin(pv.values) * 0.8)
            for (i, j), v in np.ndenumerate(pv.values):
                if not np.isnan(v):
                    ax.text(j, i, kfmt(v), ha="center", va="center", fontsize=8.5,
                            color="white" if v > 45000 else INK)
            ax.set_xticks(range(pv.shape[1]), pv.columns)
            ax.set_yticks(range(pv.shape[0]), pv.index)
            ax.tick_params(length=0)
            for sp in ax.spines.values():
                sp.set_visible(False)
        elif name == "Discount by Store Type":
            ax = view(fig, x, y, w, h, title, sub, left=44)
            g = act.groupby(["Store_Type", "Discount"]).Value.mean().unstack()
            ys = np.arange(len(g))
            for k, (flag, color) in enumerate([("No", GREY), ("Yes", BLUE)]):
                bars = ax.barh(ys + (k - 0.5) * 0.4, g[flag], height=0.36, color=color, label=f"Discount: {flag}")
                ax.bar_label(bars, [kfmt(v) for v in g[flag]], padding=3, fontsize=8, color=INK_2)
            ax.set_yticks(ys, g.index)
            ax.invert_yaxis()
            ax.xaxis.set_major_formatter(K)
            ax.set_xlim(0, g.values.max() * 1.22)
            ax.legend(loc="upper right", frameon=False, fontsize=8)
        elif name == "Uplift by Location":
            ax = view(fig, x, y, w, h, title, sub, left=44)
            up = act.groupby("Location_Type").apply(
                lambda d: d[d.Discount == "Yes"].Value.mean() / d[d.Discount == "No"].Value.mean() - 1)
            bars = ax.barh(up.index, up.values, color=BLUE, height=0.55)
            ax.bar_label(bars, [f"{v:.1%}" for v in up.values], padding=3, fontsize=8.5, color=INK_2)
            ax.invert_yaxis()
            ax.set_xlim(0, up.max() * 1.25)
            ax.xaxis.set_major_formatter(PCT)
        elif name == "Forecast Window":
            ax = view(fig, x, y, w, h, title, sub, left=50)
            win = s[s.Period.isin(["Hold-out", "Future"])]
            for series, color in [("Actual", BLUE), ("Forecast", ORANGE)]:
                d = win[win.Series == series].groupby("Date").Value.sum() / 1e6
                ax.plot(d.index, d.values, color=color, lw=1.6, label=series)
            ax.axvline(pd.Timestamp("2019-06-01"), color=INK_2, lw=1, ls="--")
            ax.text(pd.Timestamp("2019-06-02"), ax.get_ylim()[1] * 0.97, "forecast starts", fontsize=8,
                    color=INK_2, va="top")
            ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%d %b"))
            ax.legend(loc="upper left", frameon=False, fontsize=8.5, ncols=2)
        elif name == "Holdout Scatter":
            ax = view(fig, x, y, w, h, title, sub, left=46, bottom=40)
            st = hold.pivot_table(index="Store_id", columns="Series", values="Value", aggfunc="sum") / 1e6
            lim = [0, st.values.max() * 1.05]
            ax.plot(lim, lim, color=INK_2, lw=1, ls="--")
            ax.scatter(st.Actual, st.Forecast, s=22, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.6)
            ax.set_xlim(lim)
            ax.set_ylim(lim)
            ax.set_xlabel("Actual (M)", fontsize=8.5)
            ax.set_ylabel("Forecast (M)", fontsize=8.5)
        elif name == "WAPE by Store Type":
            ax = view(fig, x, y, w, h, title, sub, left=40)
            hf = hold[hold.Series == "Forecast"].groupby("Store_Type").Abs_Error.sum()
            ha = hold[hold.Series == "Actual"].groupby("Store_Type").Value.sum()
            wt = hf / ha
            bars = ax.barh(wt.index, wt.values, color=BLUE, height=0.55)
            ax.bar_label(bars, [f"{v:.1%}" for v in wt.values], padding=3, fontsize=8.5, color=INK_2)
            ax.invert_yaxis()
            ax.set_xlim(0, wt.max() * 1.3)
            ax.xaxis.set_major_formatter(PCT)
        elif name == "Model Leaderboard":
            ax = view(fig, x, y, w, h, title, sub, left=300)
            colors = [ORANGE if f == "Final model" else GREY for f in models.Final]
            bars = ax.barh(models.Model, models.WAPE, color=colors, height=0.62)
            ax.bar_label(bars, [f"{v:.1%}" for v in models.WAPE], padding=3, fontsize=8, color=INK_2)
            ax.invert_yaxis()
            ax.set_xlim(0, models.WAPE.max() * 1.15)
            ax.xaxis.set_major_formatter(PCT)
            ax.tick_params(axis="y", labelsize=7.8)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
    inner_w = W - 2 * PAD
    y = PAD
    for h, items in tb.plan():
        x = PAD
        for kind, what, share in items:
            w = inner_w * share
            if kind == "sheet":
                draw(what, x, y, w, h)
            elif kind == "header":
                box(fig, x, y, w, h, NAVY)
                runs_text(fig, x + 22, y + 14, what)
            elif kind == "accent":
                fig.patches.append(mpl.patches.Rectangle((fx(x + 5), fy(y + h)), (w - 10) / W, h / H,
                                                         transform=fig.transFigure, facecolor=ORANGE))
            else:
                runs_text(fig, x + 14, y + 12, what)
            x += w
        y += h + GAP
    fig.savefig(OUT / "dashboard_preview.png", dpi=150, facecolor=BG)
    print(OUT / "dashboard_preview.png")


if __name__ == "__main__":
    main()
