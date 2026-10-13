"""Side-by-side flat comparison: one table definition shared by the app screen and the PDF sent to clients."""
from __future__ import annotations

import datetime as dt
import io
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from flask import current_app, g

from app.core import crypto
from app.core.errors import ApiError
from app.extensions import db
from app.models import Project, Tower, Unit

MAX_FLATS = 6

STATUS_LABELS = {"vacant": "Vacant", "for_sale": "For sale", "for_rent": "For rent", "on_hold": "On hold", "booked": "Booked",
                 "sold": "Sold", "rented": "Rented", "self_occupied": "Self occupied"}
STAGES = {"ready": "Ready to move", "under_construction": "Under construction", "upcoming": "Upcoming"}
KINDS = {"apartment": "Flat", "villa": "Villa", "shop": "Shop", "office": "Office", "plot": "Plot"}


def _indian_digits(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts) + "," + tail
    return ("-" if n < 0 else "") + s


def inr(v, rupee: str = "₹") -> str:
    """₹1.25 Cr / ₹85 L / ₹45,000, the way brokers quote prices."""
    n = float(v)
    trim = lambda x: f"{x:.2f}".rstrip("0").rstrip(".")  # noqa: E731
    if n >= 1e7:
        return f"{rupee}{trim(n / 1e7)} Cr"
    if n >= 1e5:
        return f"{rupee}{trim(n / 1e5)} L"
    return f"{rupee}{_indian_digits(round(n))}"


def _floor(f: int) -> str:
    if f == 0:
        return "Ground"
    suffix = "th" if 10 <= f % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(f % 10, "th")
    return f"{f}{suffix} floor"


def load_units(ids: list[uuid.UUID]) -> list[Unit]:
    """The flats in the order given. Unknown, deleted or other-workspace ids are an error, so a client never gets a short list silently."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ApiError(422, "validation_error", "Pick at least one flat to compare", {"unit_ids": "Pick at least one flat"})
    if len(ids) > MAX_FLATS:
        raise ApiError(422, "validation_error", f"You can compare up to {MAX_FLATS} flats at a time", {"unit_ids": f"Up to {MAX_FLATS} flats"})
    rows = {u.id: u for u in db.session.query(Unit).filter(Unit.id.in_(ids), Unit.workspace_id == g.workspace.id, Unit.deleted_at.is_(None)).all()}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise ApiError(404, "not_found", "One of these flats no longer exists. Remove it from the comparison and try again.", {"missing": [str(i) for i in missing]})
    return [rows[i] for i in ids]


def build(units: list[Unit], rupee: str = "₹") -> dict:
    """Columns (one per flat) and rows (one per attribute). Rows where every flat is blank are dropped.
    `best` marks the cheapest price, cheapest rate and biggest area when at least two flats have a value."""
    towers = {t.id: t for t in db.session.query(Tower).filter(Tower.id.in_({u.tower_id for u in units})).all()}
    projects = {p.id: p for p in db.session.query(Project).filter(Project.id.in_({u.project_id for u in units})).all()}
    flats = []
    for u in units:
        t, p = towers.get(u.tower_id), projects.get(u.project_id)
        flats.append({"id": str(u.id), "number": u.number, "title": f"Flat {u.number}", "subtitle": " · ".join(x for x in (t.name if t else None, p.name if p else None) if x),
                      "project_id": str(u.project_id), "tower_id": str(u.tower_id), "status": u.status})

    def num(v):
        return float(v) if v is not None else None

    def rate(u):
        return num(u.sale_price) / num(u.area_sqft) if u.sale_price and u.area_sqft else None

    def stage(p: Project | None):
        if p is None:
            return None
        s = STAGES.get(p.stage, p.stage)
        return f"{s}, possession {p.possession_date:%b %Y}" if p.possession_date and p.stage != "ready" else s

    def where(p: Project | None):
        return ", ".join(x for x in (p.sector, p.locality, p.city) if x) if p else None

    spec = [
        ("price", "Price", [num(u.sale_price) for u in units], lambda v: inr(v, rupee), "min"),
        ("rate", "Price per sq ft", [rate(u) for u in units], lambda v: f"{rupee}{_indian_digits(round(v))}", "min"),
        ("rent", "Monthly rent", [num(u.monthly_rent) for u in units], lambda v: f"{inr(v, rupee)}/mo", "min"),
        ("bhk", "Size", [u.bhk for u in units], str, None),
        ("area", "Area", [num(u.area_sqft) for u in units], lambda v: f"{_indian_digits(round(v))} sq ft", "max"),
        ("floor", "Floor", [u.floor for u in units], _floor, None),
        ("facing", "Facing", [u.facing for u in units], str, None),
        ("status", "Availability", [u.status for u in units], lambda v: STATUS_LABELS.get(v, v), None),
        ("kind", "Type", [u.kind for u in units] if any(u.kind != "apartment" for u in units) else [None] * len(units), lambda v: KINDS.get(v, v), None),
        ("tower", "Tower", [towers[u.tower_id].name if u.tower_id in towers else None for u in units], str, None),
        ("project", "Project", [projects[u.project_id].name if u.project_id in projects else None for u in units], str, None),
        ("location", "Location", [where(projects.get(u.project_id)) or None for u in units], str, None),
        ("stage", "Possession", [stage(projects.get(u.project_id)) for u in units], str, None),
        ("developer", "Developer", [projects[u.project_id].developer if u.project_id in projects else None for u in units], str, None),
        ("rera", "RERA", [projects[u.project_id].rera_id if u.project_id in projects else None for u in units], str, None),
        ("amenities", "Amenities", [", ".join(projects[u.project_id].amenities[:6]) if u.project_id in projects and projects[u.project_id].amenities else None for u in units], str, None),
    ]
    rows = []
    for key, label, values, fmt, best in spec:
        if all(v is None or v == "" for v in values):
            continue
        present = [v for v in values if v is not None]
        winners: list[int] = []
        if best and len(present) >= 2 and len(set(present)) > 1:
            target = min(present) if best == "min" else max(present)
            winners = [i for i, v in enumerate(values) if v == target]
        texts = [fmt(v) if v is not None and v != "" else "—" for v in values]
        rows.append({"key": key, "label": label, "values": texts, "raw": values, "best": winners, "same": len(set(texts)) == 1})
    return {"flats": flats, "rows": rows}


# ---- PDF -------------------------------------------------------------------------------------------------------------

_FONTS: tuple[str, str] | None = None


def _fonts() -> tuple[str, str]:
    """A bundled font that has the ₹ sign (Helvetica doesn't). Falls back to Helvetica if the files are missing."""
    global _FONTS
    if _FONTS is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        root = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        try:
            pdfmetrics.registerFont(TTFont("CmpSans", str(root / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("CmpSans-Bold", str(root / "DejaVuSans-Bold.ttf")))
            _FONTS = ("CmpSans", "CmpSans-Bold")
        except Exception:  # pragma: no cover
            _FONTS = ("Helvetica", "Helvetica-Bold")
    return _FONTS


def render_pdf(data: dict, *, title: str, client_name: str | None, prepared_by: str, workspace_name: str, note: str | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = _fonts()
    ink, muted, brand, line, good = (colors.HexColor(c) for c in ("#0f172a", "#64748b", "#4f46e5", "#e2e8f0", "#15803d"))
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=20, leading=24, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=10, leading=14, textColor=muted),
        "head": ParagraphStyle("h", fontName=bold, fontSize=11, leading=14, textColor=colors.white),
        "headsub": ParagraphStyle("hs", fontName=regular, fontSize=8, leading=10, textColor=colors.HexColor("#c7d2fe")),
        "label": ParagraphStyle("l", fontName=regular, fontSize=9, leading=12, textColor=muted),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=9.5, leading=12.5, textColor=ink),
        "best": ParagraphStyle("b", fontName=bold, fontSize=9.5, leading=12.5, textColor=good),
        "foot": ParagraphStyle("f", fontName=regular, fontSize=8, leading=11, textColor=muted),
    }
    page = landscape(A4)
    margin = 30
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin, title=title, author=prepared_by)
    today = dt.date.today().strftime("%d %b %Y")
    els = [Paragraph(escape(title), st["title"]), Spacer(1, 4),
           Paragraph(escape(" · ".join(x for x in (f"Prepared for {client_name}" if client_name else None, f"by {prepared_by}, {workspace_name}", today) if x)), st["sub"])]
    if note:
        els += [Spacer(1, 8), Paragraph(escape(note).replace("\n", "<br/>"), st["cell"])]
    els.append(Spacer(1, 14))

    flats, rows = data["flats"], data["rows"]
    n = len(flats)
    label_w = 110
    col_w = (page[0] - 2 * margin - label_w) / max(n, 1)
    header = [Paragraph("", st["label"])] + [Paragraph(f"{escape(f['title'])}<br/><font size=8 color='#c7d2fe'>{escape(f['subtitle'])}</font>", st["head"]) for f in flats]
    table = [header]
    for r in rows:
        cells = [Paragraph(escape(r["label"]), st["label"])]
        for i, v in enumerate(r["values"]):
            cells.append(Paragraph(escape(v) + (" ✓" if i in r["best"] else ""), st["best"] if i in r["best"] else st["cell"]))
        table.append(cells)
    t = Table(table, colWidths=[label_w] + [col_w] * n, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (-1, 0), brand), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, line), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5), ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
    ]))
    els += [t, Spacer(1, 10), Paragraph("✓ marks the lowest price, lowest rate per sq ft and largest area. Prices and availability are as of " + today + " and can change; please confirm before booking.", st["foot"])]
    doc.build(els)
    return buf.getvalue()


def filename(data: dict) -> str:
    nums = "-".join(f["number"] for f in data["flats"])[:60]
    return f"Flat comparison {nums}.pdf".replace("/", "-")


# ---- public link (for WhatsApp) -------------------------------------------------------------------------------------

def public_sig(file_id) -> str:
    return crypto.sign(f"comparison-pdf|{file_id}")[:32]


def public_url(file_id) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/api/v1/public/comparisons/{file_id}/{public_sig(file_id)}.pdf"
