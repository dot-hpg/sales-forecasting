"""Build the Tableau Public workbook (tableau/Sales_Forecasting_Dashboard.twbx).

The workbook reads one long-format CSV (actuals, hold-out forecasts and the
June-July 2019 forecast in a single table) plus a small model leaderboard, so
every chart on the dashboard shares the same data source.

Run after scripts/train.py:
    python scripts/build_tableau.py
"""
from __future__ import annotations

import uuid
import zipfile
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "tableau"
DATA_DIR = "Data/tableau"  # folder inside the .twbx
EXTRACT_DIR = "Data/Extracts"  # Tableau Public only publishes extract-backed data sources
WORKBOOK = "Sales_Forecasting_Dashboard"
STARTER = "Sales_Forecasting_Starter"  # data + calculated fields + one chart, for building by hand

DS = "federated.0sales4cast7dashb0ard1hpg"
TXT = "textscan.0sales4cast7dashb0ard1hpg"
DS2 = "federated.1model5leaderb0ard2hpg9x"
TXT2 = "textscan.1model5leaderb0ard2hpg9x"

# Series colours follow a colour-blind-checked categorical order (blue, orange); grey = context.
NAVY, BLUE, ORANGE, GREY = "#1F3B73", "#2A78D6", "#EB6834", "#B7C2D0"
INK, MUTED, BG = "#1B2433", "#6B7A90", "#F3F5F9"


# --------------------------------------------------------------------------- data
def build_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["Store_id", "Store_Type", "Location_Type", "Region_Code", "Date"]
    flags = {"Holiday": {0: "Working day", 1: "Holiday"}, "Discount": {0: "No", 1: "Yes"}}

    hist = pd.read_csv(PROCESSED / "sales_clean.csv", parse_dates=["Date"])
    hist = hist[keys + ["Holiday_Flag", "Discount_Flag", "Orders", "Sales"]].rename(
        columns={"Holiday_Flag": "Holiday", "Discount_Flag": "Discount", "Sales": "Value"})
    hist["Series"] = "Actual"
    hist["Period"] = (hist["Date"] >= "2019-04-01").map({True: "Hold-out", False: "Training"})

    hold = pd.read_csv(PROCESSED / "holdout_predictions.csv", parse_dates=["Date"])
    hold["Abs_Error"] = hold["Error"].abs()
    hold = hold[keys + ["Holiday", "Discount", "Forecast", "Abs_Error"]].rename(columns={"Forecast": "Value"})
    hold["Series"], hold["Period"] = "Forecast", "Hold-out"

    fut = pd.read_csv(PROCESSED / "test_forecast.csv", parse_dates=["Date"])
    fut = fut[keys + ["Holiday", "Discount", "Forecast"]].rename(columns={"Forecast": "Value"})
    fut["Series"], fut["Period"] = "Forecast", "Future"

    for df in (hold, fut):
        for col, mapping in flags.items():
            df[col] = df[col].map(mapping)

    cols = keys + ["Holiday", "Discount", "Period", "Series", "Value", "Orders", "Abs_Error"]
    sales = pd.concat([hist, hold, fut], ignore_index=True)[cols]
    sales["Value"] = sales["Value"].round(2)
    sales["Abs_Error"] = sales["Abs_Error"].round(2)
    sales["Orders"] = sales["Orders"].astype("Int64")
    sales = sales.sort_values(["Date", "Store_id", "Series"]).reset_index(drop=True)

    models = pd.read_csv(PROCESSED / "model_comparison.csv")
    models = models.sort_values("WAPE_%").reset_index(drop=True)
    # A rank prefix keeps the bars in leaderboard order without a custom sort.
    models["Model"] = [f"{i + 1:02d}. {m}" for i, m in enumerate(models["model"])]
    models = models[["Model", "WAPE_%", "MAPE_%", "R2"]].rename(
        columns={"WAPE_%": "WAPE", "MAPE_%": "MAPE"})
    models[["WAPE", "MAPE"]] = (models[["WAPE", "MAPE"]] / 100).round(4)
    models["R2"] = models["R2"].round(3)
    models["Final"] = ["Final model" if i == 0 else "Other" for i in range(len(models))]
    return sales, models


# ----------------------------------------------------------------------- xml bits
def q(text: str) -> str:
    return escape(text, quote=True)


def sid(key: str) -> str:
    """Stable simple-id, so rebuilding the workbook gives the same file."""
    return f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_URL, key)).upper()}}}' />"


SALES_COLS = [  # (name, datatype, role, type)
    ("Store_id", "integer", "dimension", "ordinal"),
    ("Store_Type", "string", "dimension", "nominal"),
    ("Location_Type", "string", "dimension", "nominal"),
    ("Region_Code", "string", "dimension", "nominal"),
    ("Date", "date", "dimension", "ordinal"),
    ("Holiday", "string", "dimension", "nominal"),
    ("Discount", "string", "dimension", "nominal"),
    ("Period", "string", "dimension", "nominal"),
    ("Series", "string", "dimension", "nominal"),
    ("Value", "real", "measure", "quantitative"),
    ("Orders", "integer", "measure", "quantitative"),
    ("Abs_Error", "real", "measure", "quantitative"),
]
MODEL_COLS = [
    ("Model", "string", "dimension", "nominal"),
    ("WAPE", "real", "measure", "quantitative"),
    ("MAPE", "real", "measure", "quantitative"),
    ("R2", "real", "measure", "quantitative"),
    ("Final", "string", "dimension", "nominal"),
]

# Calculated fields: id -> (caption, formula, format)
CALCS = {
    "Calculation_1001": ("Actual Sales", 'IF [Series] = "Actual" THEN [Value] END', "n#,##0"),
    "Calculation_1002": ("Forecast Sales", 'IF [Series] = "Forecast" THEN [Value] END', "n#,##0"),
    "Calculation_1003": ("Discount Uplift",
                         'AVG(IF [Series] = "Actual" AND [Discount] = "Yes" THEN [Value] END) / '
                         'AVG(IF [Series] = "Actual" AND [Discount] = "No" THEN [Value] END) - 1', "p0.0%"),
    "Calculation_1004": ("Holiday Effect",
                         'AVG(IF [Series] = "Actual" AND [Holiday] = "Holiday" THEN [Value] END) / '
                         'AVG(IF [Series] = "Actual" AND [Holiday] = "Working day" THEN [Value] END) - 1', "p0.0%"),
    "Calculation_1005": ("Hold-out Actual",
                         'IF [Period] = "Hold-out" AND [Series] = "Actual" THEN [Value] END', "n#,##0"),
    "Calculation_1006": ("Hold-out Forecast",
                         'IF [Period] = "Hold-out" AND [Series] = "Forecast" THEN [Value] END', "n#,##0"),
    "Calculation_1007": ("Hold-out WAPE", "SUM([Abs_Error]) / SUM([Calculation_1005])", "p0.0%"),
    "Calculation_1008": ("Forecast Bias",
                         "SUM([Calculation_1006]) / SUM([Calculation_1005]) - 1", "p0.0%"),
    "Calculation_1009": ("Jun-Jul 2019 Forecast",
                         'IF [Period] = "Future" THEN [Value] END', "n#,##0"),
    "Calculation_1010": ("Total Sales (bn)", "SUM([Calculation_1001]) / 1000000000", "n#,##0.00"),
    "Calculation_1011": ("Jun-Jul Forecast (M)", "SUM([Calculation_1009]) / 1000000", "n#,##0.0"),
    # Average daily chain total within each mark, so partial weeks at the edges don't dip.
    "Calculation_1012": ("Avg Daily Chain Sales", "SUM([Value]) / COUNTD([Date])", "n#,##0"),
}
FORMATS = {"WAPE": "p0.0%", "MAPE": "p0.0%"}


def col_decl(name, datatype, role, typ, ds_calcs=None):
    if ds_calcs and name in ds_calcs:
        cap, formula, fmt = ds_calcs[name]
        return (f"<column caption='{q(cap)}' datatype='real' default-format='{q(fmt)}' "
                f"name='[{name}]' role='measure' type='quantitative'>"
                f"<calculation class='tableau' formula='{q(formula)}' /></column>")
    fmt = f" default-format='{q(FORMATS[name])}'" if name in FORMATS else ""
    return f"<column datatype='{datatype}'{fmt} name='[{q(name)}]' role='{role}' type='{typ}' />"


def palette(field, mapping):
    maps = "".join(f"<map to='{c}'><bucket>&quot;{q(v)}&quot;</bucket></map>" for v, c in mapping.items())
    return f"<encoding attr='color' field='[{field}]' type='palette'>{maps}</encoding>"


REMOTE_TYPES = {"string": 129, "integer": 20, "real": 5, "date": 133}
OM = "_.fcp.ObjectModelEncapsulateLegacy"  # feature-flag prefixes, as Tableau 2021.2 writes them


def datasource(name, txt, caption, filename, cols, calcs=None, colors="", rows=0):
    """A CSV data source in the 2021.2 file format (object model with legacy relation)."""
    csv_cols = "".join(f"<column datatype='{d}' name='{q(n)}' ordinal='{i}' />"
                       for i, (n, d, _, _) in enumerate(cols))
    table = filename.replace(".csv", "#csv")
    obj = f"{filename}_{uuid.uuid5(uuid.NAMESPACE_URL, filename).hex.upper()}"
    columns = (f"<columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{csv_cols}</columns>")
    attrs = f"connection='{txt}' name='{q(filename)}' table='[{q(table)}]' type='table'"
    records = "".join(
        f"<metadata-record class='column'><remote-name>{q(n)}</remote-name>"
        f"<remote-type>{REMOTE_TYPES[d]}</remote-type><local-name>[{q(n)}]</local-name>"
        f"<parent-name>[{q(filename)}]</parent-name><remote-alias>{q(n)}</remote-alias>"
        f"<ordinal>{i}</ordinal><local-type>{d}</local-type>"
        f"<aggregation>{'Sum' if d in ('integer', 'real') else ('Year' if d == 'date' else 'Count')}</aggregation>"
        f"<contains-null>true</contains-null>"
        f"<{OM}.true...object-id>[{q(obj)}]</{OM}.true...object-id></metadata-record>"
        for i, (n, d, _, _) in enumerate(cols))
    decls = "".join(col_decl(n, d, r, t) for n, d, r, t in cols)
    decls += "".join(col_decl(cid, None, None, None, calcs) for cid in (calcs or {}))
    decls += (f"<_.fcp.ObjectModelTableType.true...column caption='{q(filename)}' datatype='table' "
              f"name='[__tableau_internal_object_id__].[{q(obj)}]' role='measure' type='quantitative' />")
    style = f"<style><style-rule element='mark'>{colors}</style-rule></style>" if colors else ""
    hyper = f"{EXTRACT_DIR}/{filename.replace('.csv', '.hyper')}"
    extract_records = records.replace(f"<parent-name>[{q(filename)}]</parent-name>", "<parent-name>[Extract]</parent-name>")
    extract = f"""
      <extract _.fcp.ObjectModelExtractV2.true...object-id='' count='-1' enabled='true' units='records'>
        <connection access_mode='readonly' authentication='auth-none' author-locale='en_US' class='hyper' dbname='{q(hyper)}' default-settings='yes' schema='Extract' sslmode='' tablename='Extract' update-time='10/28/2026 07:00:00 AM' username='tableau_internal_user'>
          <{OM}.false...relation name='Extract' table='[Extract].[Extract]' type='table' />
          <{OM}.true...relation name='Extract' table='[Extract].[Extract]' type='table' />
          <refresh increment-key='' incremental-updates='false'>
            <refresh-event add-from-file-path='{q(filename.replace('.csv', ''))}' increment-value='%null%' refresh-type='create' rows-inserted='{rows}' timestamp-start='2026-10-28 07:00:00.000' />
          </refresh>
          <metadata-records>{extract_records}</metadata-records>
        </connection>
      </extract>"""
    return f"""
    <datasource caption='{q(caption)}' inline='true' name='{name}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{q(filename)}' name='{txt}'>
            <connection class='textscan' directory='{DATA_DIR}' filename='{q(filename)}' password='' server='' />
          </named-connection>
        </named-connections>
        <{OM}.false...relation {attrs}>{columns}</{OM}.false...relation>
        <{OM}.true...relation {attrs}>{columns}</{OM}.true...relation>
        <metadata-records>{records}</metadata-records>
      </connection>
      <aliases enabled='yes' />
      {decls}
      {extract}
      {style}
      <{OM}.true...object-graph>
        <objects>
          <object caption='{q(filename)}' id='{q(obj)}'>
            <properties context=''><relation {attrs}>{columns}</relation></properties>
            <properties context='extract'><relation name='Extract' table='[Extract].[Extract]' type='table' /></properties>
          </object>
        </objects>
      </{OM}.true...object-graph>
    </datasource>"""


# Shelf fields: short key -> (column, derivation, instance-prefix, suffix, type)
def inst(column, derivation):
    prefix, suffix, typ = {
        "None": ("none", "nk", "nominal"), "Sum": ("sum", "qk", "quantitative"),
        "Avg": ("avg", "qk", "quantitative"), "User": ("usr", "qk", "quantitative"),
        "Week-Trunc": ("twk", "qk", "quantitative"), "Weekday": ("wd", "ok", "ordinal"),
        "Ordinal": ("none", "ok", "ordinal"),
    }[derivation]
    deriv = "None" if derivation == "Ordinal" else derivation
    name = f"[{prefix}:{column}:{suffix}]"
    return name, f"<column-instance column='[{column}]' derivation='{deriv}' name='{name}' pivot='key' type='{typ}' />"


def worksheet(name, title, ds, ds_caption, ds_cols, calcs, rows, cols, mark, enc=None, labels=False,
              subtitle="", ban=None):
    """rows/cols: lists of (column, derivation); enc: {encoding: (column, derivation)}."""
    enc = enc or {}
    used = {}
    for c, d in rows + cols + list(enc.values()):
        used[(c, d)] = inst(c, d)
    base_cols = {c for c, _ in used}
    deps = ""
    lookup = {n: (n, d, r, t) for n, d, r, t in ds_cols}
    needed, todo = set(), list(base_cols)
    while todo:  # calcs pull in the fields they reference
        c = todo.pop()
        if c in needed:
            continue
        needed.add(c)
        if c in calcs:
            todo += [n for n in list(lookup) + list(calcs) if f"[{n}]" in calcs[c][1]]
    for c in sorted(needed):
        deps += col_decl(c, None, None, None, calcs) if c in calcs else col_decl(*lookup[c])
    deps += "".join(x for _, x in used.values())

    def shelf(items):
        if not items:
            return "<rows />" if items is rows else "<cols />"
        refs = [f"[{ds}].{used[(c, d)][0]}" for c, d in items]
        return refs[0] if len(refs) == 1 else "(" + " / ".join(refs) + ")"

    encodings = "".join(f"<{e} column='[{ds}].{used[(c, d)][0]}' />" for e, (c, d) in enc.items())
    label_style = ("<style><style-rule element='mark'><format attr='mark-labels-show' value='true' />"
                   "<format attr='mark-labels-cull' value='true' /></style-rule></style>") if labels else ""
    sub = (f"<run>Æ&#10;</run><run fontcolor='{MUTED}' fontsize='9'>{q(subtitle)}</run>") if subtitle else ""
    big_number = ""
    if ban:  # big-number KPI tile: value plus a unit, styled as one label
        c, d = enc["text"]
        big_number = (f"<customized-label><formatted-text><run bold='true' fontcolor='{INK}' fontsize='26'>"
                      f"&lt;[{ds}].{used[(c, d)][0]}&gt;</run>"
                      + (f"<run fontcolor='{MUTED}' fontsize='13'>{q(ban)}</run>" if ban.strip() else "")
                      + "</formatted-text></customized-label>")
    rows_xml = f"<rows>{shelf(rows)}</rows>" if rows else "<rows />"
    cols_xml = f"<cols>{shelf(cols)}</cols>" if cols else "<cols />"
    return f"""
    <worksheet name='{q(name)}'>
      <layout-options>
        <title>
          <formatted-text><run bold='true' fontcolor='{INK}' fontsize='12'>{q(title)}</run>{sub}</formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources><datasource caption='{q(ds_caption)}' name='{ds}' /></datasources>
          <datasource-dependencies datasource='{ds}'>{deps}</datasource-dependencies>
          <aggregation value='true' />
        </view>
        <style />
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='{mark}' />
            {f"<encodings>{encodings}</encodings>" if encodings else ""}
            {big_number}
            {label_style}
          </pane>
        </panes>
        {rows_xml}
        {cols_xml}
      </table>
      {sid('worksheet/' + name)}
    </worksheet>"""


S, M = "Sales", "Models"
SHEETS = []


def add(name, title, rows, cols, mark, enc=None, labels=False, subtitle="", models=False, ban=None):
    ds, cap, dcols, calcs = (DS2, M, MODEL_COLS, {}) if models else (DS, S, SALES_COLS, CALCS)
    SHEETS.append(name)
    return worksheet(name, title, ds, cap, dcols, calcs, rows, cols, mark, enc, labels, subtitle, ban)


def build_worksheets() -> str:
    a = "Calculation_1001"
    ws = [
        add("KPI Total Sales", "TOTAL SALES TO DATE", [], [], "Text",
            {"text": ("Calculation_1010", "User")}, ban=" bn"),
        add("KPI Discount Uplift", "DISCOUNT UPLIFT (SALES/DAY)", [], [], "Text", {"text": ("Calculation_1003", "User")}, ban=" "),
        add("KPI Holiday Effect", "HOLIDAY EFFECT (SALES/DAY)", [], [], "Text", {"text": ("Calculation_1004", "User")}, ban=" "),
        add("KPI Hold-out WAPE", "HOLD-OUT ERROR (WAPE)", [], [], "Text", {"text": ("Calculation_1007", "User")}, ban=" "),
        add("KPI Forecast", "JUN – JUL 2019 FORECAST", [], [], "Text", {"text": ("Calculation_1011", "User")}, ban=" M"),
        add("Sales Trend", "Chain sales by week: actuals and 61-day forecast",
            [("Calculation_1012", "User")], [("Date", "Week-Trunc")], "Line", {"color": ("Series", "None")},
            subtitle="Orange overlaps blue in Apr–May 2019 (hold-out test), then carries on alone for Jun–Jul 2019"),
        add("Store Type x Location", "Average daily sales per store: format × location",
            [("Store_Type", "None")], [("Location_Type", "None")], "Square",
            {"color": (a, "Avg"), "text": (a, "Avg")}, subtitle="S4 stores in L2 locations sell the most"),
        add("Discount by Store Type", "Discounts lift sales in every store type",
            [("Store_Type", "None"), ("Discount", "None")], [(a, "Avg")], "Bar",
            {"color": ("Discount", "None")}, labels=True, subtitle="Average daily sales per store, discount vs no discount"),
        add("Weekday Pattern", "Weekends are the peak",
            [(a, "Avg")], [("Date", "Weekday")], "Bar", labels=True,
            subtitle="Average daily sales per store by weekday"),
        add("Region Sales", "Region matters little",
            [("Region_Code", "None")], [(a, "Avg")], "Bar", labels=True,
            subtitle="Average daily sales per store"),
        add("Holdout Scatter", "Hold-out test: actual vs forecast per store",
            [("Calculation_1006", "Sum")], [("Calculation_1005", "Sum")], "Circle",
            {"lod": ("Store_id", "Ordinal")},
            subtitle="Each dot is one store's Apr–May 2019 total; on the diagonal = perfect"),
        add("WAPE by Store Type", "Forecast error by store type",
            [("Store_Type", "None")], [("Calculation_1007", "User")], "Bar", labels=True, subtitle="Hold-out WAPE, store × day"),
        add("Model Leaderboard", "10 models, 3-fold time-series cross-validation",
            [("Model", "None")], [("WAPE", "Sum")], "Bar", {"color": ("Final", "None")}, labels=True,
            subtitle="WAPE, lower is better", models=True),
    ]
    return "<worksheets>" + "".join(ws) + "</worksheets>"


# ---------------------------------------------------------------------- dashboard
W, H = 1300, 2260


def zone(zid, x, y, w, h, inner="", **attrs):
    sx, sy = 100000 / W, 100000 / H
    extra = "".join(f" {k.replace('_', '-')}='{q(str(v))}'" for k, v in attrs.items())
    return (f"<zone h='{round(h * sy)}' id='{zid}' w='{round(w * sx)}' x='{round(x * sx)}' "
            f"y='{round(y * sy)}'{extra}>{inner}</zone>")


def card_style(bg="#FFFFFF", margin=6, padding=8):
    return (f"<zone-style><format attr='border-color' value='#E1E6EF' /><format attr='border-style' value='solid' />"
            f"<format attr='border-width' value='1' /><format attr='margin' value='{margin}' />"
            f"<format attr='padding' value='{padding}' /><format attr='background-color' value='{bg}' /></zone-style>")


def text_zone(zid, x, y, w, h, runs, bg=None):
    style = (f"<zone-style><format attr='border-style' value='none' /><format attr='margin' value='6' />"
             f"<format attr='padding' value='14' /><format attr='background-color' value='{bg}' /></zone-style>"
             if bg else "")
    return zone(zid, x, y, w, h, f"<formatted-text>{runs}</formatted-text>{style}", type="text")


def build_dashboard() -> str:
    zid = iter(range(10, 200))
    pad = 16
    inner_w = W - 2 * pad
    z = []
    # header band
    z.append(text_zone(next(zid), pad, pad, inner_w, 120,
                       f"<run bold='true' fontcolor='#FFFFFF' fontsize='24'>Product Sales Forecasting</run>"
                       f"<run>Æ&#10;</run><run fontcolor='#C9D6EA' fontsize='11'>365 retail stores · 4 formats · "
                       f"5 location types · 4 regions · daily data Jan 2018 – May 2019 · LightGBM forecast for "
                       f"Jun – Jul 2019</run>", bg=NAVY))
    y = pad + 120 + 8
    # KPI row
    kpis = ["KPI Total Sales", "KPI Discount Uplift", "KPI Holiday Effect", "KPI Hold-out WAPE", "KPI Forecast"]
    kw = inner_w / len(kpis)
    for i, name in enumerate(kpis):
        z.append(zone(next(zid), pad + i * kw, y, kw, 120, card_style(), name=name))
    y += 120 + 8
    # trend
    z.append(zone(next(zid), pad, y, inner_w, 420, card_style(), name="Sales Trend"))
    y += 420 + 8
    half = inner_w / 2
    rows = [("Store Type x Location", "Discount by Store Type", 380),
            ("Weekday Pattern", "Region Sales", 330),
            ("Holdout Scatter", "WAPE by Store Type", 400)]
    for left, right, h in rows:
        z.append(zone(next(zid), pad, y, half, h, card_style(), name=left))
        z.append(zone(next(zid), pad + half, y, half, h, card_style(), name=right))
        y += h + 8
    z.append(zone(next(zid), pad, y, inner_w, 330, card_style(), name="Model Leaderboard"))
    y += 330 + 8
    z.append(text_zone(next(zid), pad, y, inner_w, H - y - pad,
                       f"<run fontcolor='{MUTED}' fontsize='9'>Final model: global LightGBM on log sales with "
                       f"61-day-shifted lags (no order leakage). Cross-validated WAPE 15.3% vs 22.8% for a seasonal "
                       f"naive baseline. Hold-out Apr–May 2019: store-day WAPE 16.8%, store-total WAPE 10.5%. "
                       f"WAPE = sum of absolute errors ÷ sum of sales. Code, notebook and app: "
                       f"github.com/dot-hpg/sales-forecasting</run>"))
    root_style = "<zone-style><format attr='border-style' value='none' /><format attr='margin' value='0' /></zone-style>"
    root = (f"<zone h='100000' id='1' type='layout-basic' w='100000' x='0' y='0'>{''.join(z)}{root_style}</zone>")
    return f"""
  <dashboards>
    <dashboard name='Sales Forecasting Dashboard'>
      <style><style-rule element='table'><format attr='background-color' value='{BG}' /></style-rule></style>
      <size maxheight='{H}' maxwidth='{W}' minheight='{H}' minwidth='{W}' />
      <zones>{root}</zones>
      {sid('dashboard')}
    </dashboard>
  </dashboards>"""


def build_windows(dashboard=True) -> str:
    cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' />"
             "<card type='marks' /></strip></edge><edge name='top'><strip size='2147483647'>"
             "<card type='columns' /></strip><strip size='2147483647'><card type='rows' /></strip>"
             "<strip size='31'><card type='title' /></strip></edge></cards>")
    views = "".join(f"<viewpoint name='{q(s)}' />" for s in SHEETS)
    out = "" if not dashboard else (f"<window class='dashboard' maximized='true' name='Sales Forecasting Dashboard'>"
           f"<viewpoints>{views}</viewpoints><active id='16' />{sid('window/dashboard')}</window>")
    out += "".join(f"<window class='worksheet' name='{q(s)}'>{cards}{sid('window/' + s)}</window>"
                   for s in SHEETS)
    return f"<windows source-height='30'>{out}</windows>"


def build_workbook(starter: bool = False) -> str:
    """Full dashboard, or (starter) just the data sources, calculated fields and one chart."""
    sales_colors = (palette("none:Series:nk", {"Actual": BLUE, "Forecast": ORANGE})
                    + palette("none:Discount:nk", {"Yes": BLUE, "No": GREY}))
    model_colors = palette("none:Final:nk", {"Final model": ORANGE, "Other": GREY})
    SHEETS.clear()
    if starter:
        worksheets = "<worksheets>" + add(
            "Sales Trend", "Chain sales by week: actuals and 61-day forecast",
            [("Calculation_1012", "User")], [("Date", "Week-Trunc")], "Line",
            {"color": ("Series", "None")}) + "</worksheets>"
    else:
        worksheets = build_worksheets()
    return f"""<?xml version='1.0' encoding='utf-8' ?>
<!-- build 20212.21.0712.0907                               -->
<workbook original-version='18.1' source-build='2021.2.1 (20212.21.0712.0907)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <_.fcp.ObjectModelEncapsulateLegacy.true...ObjectModelEncapsulateLegacy />
    <_.fcp.ObjectModelExtractV2.true...ObjectModelExtractV2 />
    <_.fcp.ObjectModelTableType.true...ObjectModelTableType />
    <SheetIdentifierTracking />
    <WindowsPersistSimpleIdentifiers />
  </document-format-change-manifest>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
    {datasource(DS, TXT, S, "tableau_sales.csv", SALES_COLS, CALCS, sales_colors, ROWS["tableau_sales.csv"])}
    {datasource(DS2, TXT2, M, "tableau_models.csv", MODEL_COLS, None, model_colors, ROWS["tableau_models.csv"])}
  </datasources>
  {worksheets}
  {"" if starter else build_dashboard()}
  {build_windows(dashboard=not starter)}
</workbook>
"""


ROWS: dict[str, int] = {}
HYPER_TYPES = {"string": "text", "integer": "big_int", "real": "double", "date": "date"}


def write_hyper(df: pd.DataFrame, cols, path: Path) -> None:
    """Write df to a Tableau extract with the single table "Extract"."Extract"."""
    from tableauhyperapi import (Connection, CreateMode, HyperProcess, Inserter, NOT_NULLABLE, NULLABLE,
                                 SqlType, TableDefinition, TableName, Telemetry)

    path.unlink(missing_ok=True)
    table = TableDefinition(TableName("Extract", "Extract"), [
        TableDefinition.Column(n, getattr(SqlType, HYPER_TYPES[d])(),
                               NULLABLE if df[n].isna().any() else NOT_NULLABLE)
        for n, d, _, _ in cols])
    rows = []
    for rec in df[[n for n, *_ in cols]].itertuples(index=False):
        rows.append([None if pd.isna(v) else (v.date() if isinstance(v, pd.Timestamp) else
                     (int(v) if d == "integer" else float(v) if d == "real" else v))
                     for v, (_, d, _, _) in zip(rec, cols)])
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(hp.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(table)
            with Inserter(conn, table) as ins:
                ins.add_rows(rows)
                ins.execute()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sales, models = build_data()
    sales.to_csv(OUT / "tableau_sales.csv", index=False, date_format="%Y-%m-%d")
    models.to_csv(OUT / "tableau_models.csv", index=False)
    global ROWS
    ROWS = {"tableau_sales.csv": len(sales), "tableau_models.csv": len(models)}
    hyper_dir = OUT / "extracts"
    hyper_dir.mkdir(exist_ok=True)
    write_hyper(sales, SALES_COLS, hyper_dir / "tableau_sales.hyper")
    write_hyper(models, MODEL_COLS, hyper_dir / "tableau_models.hyper")
    for name, starter in [(WORKBOOK, False), (STARTER, True)]:
        twb = build_workbook(starter)
        (OUT / f"{name}.twb").write_text(twb, encoding="utf-8")
        with zipfile.ZipFile(OUT / f"{name}.twbx", "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{name}.twb", twb)
            z.write(OUT / "tableau_sales.csv", f"{DATA_DIR}/tableau_sales.csv")
            z.write(OUT / "tableau_models.csv", f"{DATA_DIR}/tableau_models.csv")
            for f in ("tableau_sales.hyper", "tableau_models.hyper"):
                z.write(hyper_dir / f, f"{EXTRACT_DIR}/{f}")
        print(f"{len(sales):,} rows -> {OUT / (name + '.twbx')}")


if __name__ == "__main__":
    main()
