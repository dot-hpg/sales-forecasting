"""Build the project submission PDF (docs/submission.pdf) from docs/links.json.

Fill in a URL in docs/links.json, then run:  python scripts/make_submission_pdf.py
Links left empty are printed as "To be added".
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
LINKS_FILE = ROOT / "docs" / "links.json"
OUT_FILE = ROOT / "docs" / "submission.pdf"
FIGURES = ROOT / "reports" / "figures"

INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
BLUE, ORANGE, PALE = "#2a78d6", "#c2410c", "#f4f7fc"


def register_fonts() -> tuple[str, str]:
    """Use DejaVu Sans when it is installed (full Unicode), else the built-in Helvetica."""
    for folder in ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts"]:
        regular, bold = Path(folder, "DejaVuSans.ttf"), Path(folder, "DejaVuSans-Bold.ttf")
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("Body", str(regular)))
            pdfmetrics.registerFont(TTFont("Body-Bold", str(bold)))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")
            return "Body", "Body-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, BOLD = register_fonts()
S = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=22, leading=27, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=10.5, leading=15, textColor=INK_2),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=13, leading=17, textColor=INK, spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.8, leading=11.5, textColor=INK),
    "cell_b": ParagraphStyle("cell_b", fontName=BOLD, fontSize=8.8, leading=11.5, textColor=INK),
    "cell_m": ParagraphStyle("cell_m", fontName=FONT, fontSize=8.3, leading=11, textColor=INK_2),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=8.3, leading=11, textColor=INK_2),
    "caption": ParagraphStyle("caption", fontName=FONT, fontSize=8, leading=10.5, textColor=MUTED),
}


def table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor(GRID)),
    ]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor(INK_2))]
    if zebra:
        style += [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(PALE)])]
    t.setStyle(TableStyle(style))
    return t


def p(text, style="cell"):
    return Paragraph(text, S[style])


def links_table(links):
    rows = [[p("Deliverable", "head"), p("Link", "head"), p("Contents", "head")]]
    for item in links:
        url = item["url"].strip()
        if url:
            shown = url.replace("https://", "")
            link = f'<link href="{url}"><font color="{BLUE}"><u>{shown}</u></font></link>'
        else:
            link = f'<font color="{ORANGE}">To be added</font>'
        rows.append([p(item["name"], "cell_b"), p(link), p(item["what"], "cell_m")])
    return table(rows, [36 * mm, 82 * mm, 56 * mm])


def build() -> Path:
    cfg = json.loads(LINKS_FILE.read_text())
    doc = SimpleDocTemplate(str(OUT_FILE), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{cfg['project']}: project submission", author=cfg["author"])
    story = [
        p(cfg["project"], "title"), Spacer(1, 3),
        p(f"Project submission · <b>{cfg['author']}</b> · GitHub "
          '<link href="https://github.com/dot-hpg"><font color="#2a78d6">@dot-hpg</font></link>', "subtitle"),
        Spacer(1, 4),
        p("Daily sales forecasts for 365 retail stores, 61 days ahead (1 June to 31 July 2019), with a global "
          "LightGBM model deployed as a mobile-friendly web app and a Flask REST API.", "subtitle"),
        p("Submission links", "h2"), links_table(cfg["links"]),
    ]

    story += [
        p("Problem and approach", "h2"),
        p("A retail chain needs a daily sales forecast per store for the next two months to plan inventory, budgets, "
          "promotions and staffing. The data covers 365 stores (4 store types, 5 location types, 4 regions) and 516 days "
          "(188,340 rows, January 2018 to May 2019) with holiday and discount flags, orders and sales.", "body"),
        Spacer(1, 5),
        p("<b>Pipeline:</b> data quality checks → EDA → 8 hypothesis tests with effect sizes → leakage-free feature "
          "engineering → rolling-origin cross-validation (three 61-day folds) → 10 models compared → final hold-out test "
          "→ Streamlit app and Flask API. <b>#Order is excluded</b> because it is only known after the day ends "
          "(target leakage), and rolling sales features are shifted by the full 61-day horizon.", "body"),
    ]

    results = [
        [p("Result", "head"), p("Value", "head")],
        [p("Cross-validation WAPE: LightGBM vs seasonal naive"), p("<b>15.3%</b> vs 22.8%")],
        [p("Chain-level WAPE: LightGBM vs SARIMAX / Prophet / Holt-Winters"), p("<b>10.4%</b> vs 14.2 / 17.2 / 18.1%")],
        [p("Hold-out Apr-May 2019, store × day WAPE (R²)"), p("<b>16.8%</b> (0.67)")],
        [p("Hold-out Apr-May 2019, store × 61-day total WAPE (R²)"), p("<b>10.5%</b> (0.83)")],
        [p("Forecast for June and July 2019, whole chain"), p("<b>989.8M</b> (−2.6% vs 2018)")],
    ]
    story += [p("Key results", "h2"), table(results, [118 * mm, 56 * mm])]

    insights = [
        [p("Finding", "head"), p("Evidence", "head"), p("Recommendation", "head")],
        [p("Discounts lift sales", "cell_b"), p("+33.5% per store, 364 of 365 stores"),
         p("Run campaigns on weaker days (Tue to Fri) and months", "cell_m")],
        [p("Holidays reduce sales", "cell_b"), p("−19%; −48% from day 2 of long holidays"),
         p("Cut staff and fresh stock, especially on long holidays", "cell_m")],
        [p("Weekends peak", "cell_b"), p("Sunday +15%, Saturday +9%"), p("Staff up and replenish before weekends", "cell_m")],
        [p("Format and location set the level", "cell_b"), p("S4 59.9K vs S2 27.5K per day; region η² = 0.03"),
         p("Prioritise S4/S3 formats in L2/L1 locations", "cell_m")],
        [p("Forecast drifts with record months", "cell_b"), p("Hold-out bias −9.8% after record May 2019"),
         p("Retrain monthly and alert if bias exceeds ±5%", "cell_m")],
    ]
    story += [KeepTogether([p("Insights and recommendations", "h2"), table(insights, [44 * mm, 62 * mm, 68 * mm])])]

    fig = FIGURES / "15_holdout_actual_vs_forecast.png"
    if fig.exists():
        w = 174 * mm
        story += [KeepTogether([Spacer(1, 10), Image(str(fig), width=w, height=w * 601 / 2084),
                                p("Hold-out test: daily chain sales, actual vs 61-day-ahead forecast (April to May 2019).",
                                  "caption")])]

    checklist = [
        [p("Brief requirement", "head"), p("Where it is", "head")],
        [p("Tableau visualisation"), p("Tableau Public dashboard (link above); data in data/processed/", "cell_m")],
        [p("EDA and hypothesis testing"), p("Notebook sections 3 to 7; data/processed/hypothesis_results.csv", "cell_m")],
        [p("ML modelling and time-series CV"), p("Notebook sections 8 to 14; data/processed/model_comparison.csv", "cell_m")],
        [p("Deployment (serialised model + Flask API)"), p("models/*.joblib, api/app.py, Dockerfile, streamlit_app.py", "cell_m")],
        [p("README, blog and demo video"), p("README.md; blog and Loom links above", "cell_m")],
    ]
    story += [KeepTogether([p("Brief coverage", "h2"), table(checklist, [70 * mm, 104 * mm])])]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(18 * mm, 9 * mm, f"{cfg['project']} · {cfg['author']}")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUT_FILE


if __name__ == "__main__":
    print(f"Wrote {build()}")
