"""Build docs/cat_bond_concept_note.docx and .pdf (one page, Calibri 10pt, plain).

Run from the repo root: python3 scripts/build_concept_note.py
PDF is produced from the docx with LibreOffice (soffice).
"""
import subprocess
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FIG = ROOT / "data" / "event_checks" / "ian.png"
FONT, SIZE = "Calibri", 10

TITLE = "Measuring Cat Bond Capital"
SUB = "Security-level evidence on issuance demand, secondary trading and event repricing. Caro Park, PhD. October 2026."

SUMMARY = ("Cat bond data are fragmented across deal pages, security identifiers, transaction records, fund "
           "filings and loss reports. This project links them into a security-level panel to measure primary "
           "demand, secondary repricing, investor flow and changes in outstanding risk capital. Joins built and "
           "checked against two Florida landfalls and against the valuations the holding funds file.")

DATA = [
    "1,311 deals since 1996: tranche-level terms, source for each term, confidence rating.",
    "1,196 deal-to-CUSIP pairs: 700 deals linked with evidence per match, 230 more CUSIPs attributed at program "
    "level; the series names that holding funds file resolve same-month twins.",
    "68,759 cleaned TRACE trades, 1,135 CUSIPs, 2011 to 2026. Every dropped record counted by rule.",
    "48,730 deal-day panel rows, 624 traded deals, 97.9% of trades attributed; 6,467 hurricane and other hazard "
    "contracts, 2021 to 2026.",
    "132 Form N-PORT filings for seven registered cat bond funds, 2019 to 2026: monthly subscriptions, redemptions "
    "and returns, and 21,690 holdings with CUSIPs that cover 60% of the bridged universe.",
]

QUESTIONS = [
    ("Primary-market demand.", "Do upsizing and guidance tightening predict secondary performance or liquidity, "
                               "controlling for expected loss, attachment and structure?"),
    ("Event repricing.", "When catastrophe expectations move before insured loss is known, do exposed bonds reprice "
                         "relative to matched controls?"),
    ("Capital substitution.", "When do cat bond spreads and capacity move with traditional reinsurance on "
                              "comparable layers?"),
]

RELEVANCE = [
    ("ILS and cat bond managers:", "primary absorption, liquidity, loss creep, post-issue performance."),
    ("Quant and flow investors:", "testable signals, matched controls, latent capital pressure without holder data."),
    ("Insurers and reinsurers:", "execution, capacity and relative pricing by peril, structure and layer."),
]

VALID_INTRO = ("Signal is the change in catastrophe expectation; exposure is the peril and region mapped to each "
               "bond; comparison group is contemporaneous bonds without that exposure. Counts in parentheses are "
               "deals with trades on both sides of the event.")

TABLE = [
    ["Change at +60 days, pts", "Ian 2022", "Milton 2024"],
    ["Florida-exposed deals", "−3.7 (10)", "+2.0 (12)"],
    ["No hurricane exposure", "−3.7 (10)", "+0.2 (6)"],
    ["Exposed down 2+ points", "10 of 10", "1 of 12"],
    ["Contract activity peak", "week −1", "landfall week"],
]

VALID_TEXT = ("Ian: loss-bearing deals fall by tens of points; exposed median reaches −50 five weeks after "
              "landfall. The few-point decline in the unexposed group is the market-wide repricing of late 2022, "
              "not an attribution error. Milton: only exposed deals move. One sells off into landfall and recovers, "
              "the rest rally once the season's peak passes; unexposed deals stay within a fraction of a point.")

LIMITS = ("Investor net flow is now observed for the registered US funds: the Stone Ridge interval fund lost "
          "$4.0bn net from 2019 to 2024 and turned to inflows in 2025, its high-yield sibling took in $3.3bn, and "
          "the Victory Pioneer CAT Bond fund $1.5bn in fifteen months; interval-fund redemptions lag losses by a "
          "tender window. Fund valuations agree with TRACE prices to a median 0.24 points across 2,398 "
          "CUSIP-quarters, the strongest check on the joins. UCITS funds' subscriptions and redemptions sit in "
          "their public semi-annual accounts, next to be parsed. Still unobserved: private mandates and "
          "sidecars, where the Stone Ridge interval fund's Ian loss actually came through. Next: UCITS accounts, "
          "loss development from fund marks against trades, then heat, drought and public-sector risk transfer.")

CLOSE = ("I am looking to compare this framework with how practitioners observe demand, liquidity and capacity. "
         "github.com/carospark/cat-bond-issuance, github.com/carospark/cat-bond-flow-analysis.")


def set_font(run, bold=False, size=SIZE):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)


def para(container, runs, after=4, before=0, style=None, indent=None):
    p = container.add_paragraph(style=style) if style else container.add_paragraph()
    pf = p.paragraph_format
    pf.space_after, pf.space_before, pf.line_spacing = Pt(after), Pt(before), 1.0
    if indent is not None:
        pf.left_indent = Inches(indent)
        pf.first_line_indent = Inches(-indent)
    for text, bold in runs:
        set_font(p.add_run(text), bold)
    return p


def heading(container, text):
    return para(container, [(text, True)], after=1, before=5)


def no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}"); el.set(qn("w:val"), "nil"); borders.append(el)
    tblPr.append(borders)


def fixed_layout(table, widths):
    tblPr = table._tbl.tblPr
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    mar = OxmlElement("w:tblCellMar")
    for side, w in (("left", 20), ("right", 20), ("top", 0), ("bottom", 0)):
        el = OxmlElement(f"w:{side}"); el.set(qn("w:w"), str(w)); el.set(qn("w:type"), "dxa"); mar.append(el)
    tblPr.append(mar)
    for row in table.rows:
        for c, w in zip(row.cells, widths):
            c.width = w
    for col, w in zip(table.columns, widths):
        col.width = w


def cell_bottom_border(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    el = OxmlElement("w:bottom")
    el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "6"); el.set(qn("w:color"), "000000")
    b.append(el); tcPr.append(b)


def clear_cell(cell):
    cell.paragraphs[0]._element.getparent().remove(cell.paragraphs[0]._element)


def build_docx():
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(SIZE)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.6)
    sec.top_margin = sec.bottom_margin = Inches(0.5)

    para(doc, [(TITLE, True)], after=0, before=0).runs[0].font.size = Pt(13)
    para(doc, [(SUB, False)], after=4)

    heading(doc, "Summary")
    para(doc, [(SUMMARY, False)])

    heading(doc, "Data")
    for d in DATA:
        para(doc, [("\u2022  " + d, False)], after=1, indent=0.15)

    heading(doc, "Research questions")
    for i, (a, b) in enumerate(QUESTIONS, 1):
        para(doc, [(f"{i}. ", False), (a, True), (" " + b, False)], after=1, indent=0.2)

    heading(doc, "Relevance")
    for a, b in RELEVANCE:
        para(doc, [(a, True), (" " + b, False)], after=1)

    heading(doc, "Validation: the joins around two landfalls")
    para(doc, [(VALID_INTRO, False)], after=2)

    # figure left, table and text right
    lay = doc.add_table(rows=1, cols=2)
    lay.alignment = WD_TABLE_ALIGNMENT.LEFT
    lay.autofit = False
    no_borders(lay)
    lw, rw = Inches(4.25), Inches(3.05)
    fixed_layout(lay, [lw, rw])
    left, right = lay.rows[0].cells
    clear_cell(left); clear_cell(right)
    fp = left.add_paragraph(); fp.paragraph_format.space_after = Pt(2)
    fp.add_run().add_picture(str(FIG), width=Inches(4.2))
    para(left, [("Figure 1. Hurricane Ian, Florida landfall 28 September 2022.", False)], after=0)

    para(right, [("Table 1. Median price change at +60 days.", False)], after=2)
    t = right.add_table(rows=len(TABLE), cols=3)
    no_borders(t)
    t.autofit = False
    widths = [Inches(1.45), Inches(0.65), Inches(0.85)]
    fixed_layout(t, widths)
    for ri, row in enumerate(TABLE):
        for ci, val in enumerate(row):
            c = t.cell(ri, ci)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0); p.paragraph_format.space_before = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if ci else WD_ALIGN_PARAGRAPH.LEFT
            set_font(p.add_run(val), bold=(ri == 0))
            if ri == 0 or ri == len(TABLE) - 1:
                cell_bottom_border(c)
    para(right, [(VALID_TEXT, False)], after=0, before=4)

    heading(doc, "Flows, limits and next steps")
    para(doc, [(LIMITS, False)])
    para(doc, [(CLOSE, False)], after=0)

    out = DOCS / "cat_bond_concept_note.docx"
    doc.save(str(out))
    return out


if __name__ == "__main__":
    out = build_docx()
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(DOCS), str(out)],
                   check=True, capture_output=True)
    print("wrote", out, "and .pdf")
