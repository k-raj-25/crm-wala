"""Side-by-side society (project) comparison. The client gets one PDF: the comparison table, then for each society the photos,
floor plans and brochure the broker chose to send."""
from __future__ import annotations

import datetime as dt
import io
import logging
import re
import uuid
from xml.sax.saxutils import escape

from flask import g
from sqlalchemy import func

from app.core.errors import ApiError
from app.extensions import db
from app.models import FileAsset, Project, Tower, Unit
from app.services import inventory, storage
from app.services.comparison import STAGES, _fonts, _indian_digits, inr

log = logging.getLogger(__name__)

MAX_SOCIETIES = 4
MAX_AMENITY_ROWS = 24
EMAIL_LIMIT_MB = 20  # most mail servers refuse bigger attachments
PROJECT_KINDS = {"residential": "Residential", "commercial": "Commercial", "villa": "Villas", "plotted": "Plots", "mixed": "Mixed use"}


def _key(label: str | None) -> str:
    """'3 BHK', '3bhk' and ' 3 Bhk ' are the same size."""
    return re.sub(r"\s+", "", (label or "").lower())


def load_projects(ids: list[uuid.UUID]) -> list[Project]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ApiError(422, "validation_error", "Pick at least one society to compare", {"societies": "Pick at least one society"})
    if len(ids) > MAX_SOCIETIES:
        raise ApiError(422, "validation_error", f"You can compare up to {MAX_SOCIETIES} societies at a time", {"societies": f"Up to {MAX_SOCIETIES} societies"})
    rows = {p.id: p for p in db.session.query(Project).filter(Project.id.in_(ids), Project.workspace_id == g.workspace.id, Project.deleted_at.is_(None)).all()}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise ApiError(404, "not_found", "One of these societies no longer exists. Remove it from the comparison and try again.", {"missing": [str(i) for i in missing]})
    return [rows[i] for i in ids]


def _chosen_sizes(p: Project, labels: list[str] | None) -> list[dict]:
    """The project's sizes the broker kept, in the project's own order. None means all of them."""
    sizes = [z for z in (p.sizes or []) if z.get("label")]
    if labels is None:
        return sizes
    keep = {_key(x) for x in labels}
    return [z for z in sizes if _key(z["label"]) in keep]


def build(projects: list[Project], picks: dict[uuid.UUID, dict] | None = None) -> dict:
    """Columns (one per society) and rows grouped into overview, layouts and amenities. Rows where every society is blank are dropped.
    `best` marks the lowest starting price and rate, and the most flats available / amenities, when at least two societies have a value."""
    picks = picks or {}
    pids = [p.id for p in projects]
    inventory.release_expired_holds(g.workspace.id)
    counts = inventory.counts_by(Unit.project_id, pids)
    towers = dict(db.session.query(Tower.project_id, func.count()).filter(Tower.project_id.in_(pids)).group_by(Tower.project_id).all())
    live = (Unit.project_id.in_(pids), Unit.deleted_at.is_(None), Unit.status.in_(inventory.AVAILABLE))
    priced = db.session.query(Unit.project_id, func.min(Unit.sale_price), func.max(Unit.sale_price), func.avg(Unit.sale_price / func.nullif(Unit.area_sqft, 0))).filter(
        *live, Unit.sale_price.isnot(None)).group_by(Unit.project_id).all()
    prices = {pid: (lo, hi, rate) for pid, lo, hi, rate in priced}
    # per size: how many are free and the cheapest, matched on the flat's BHK
    by_size: dict[tuple, list] = {}
    for pid, bhk, n, lo in db.session.query(Unit.project_id, Unit.bhk, func.count(), func.min(Unit.sale_price)).filter(*live).group_by(Unit.project_id, Unit.bhk).all():
        cur = by_size.setdefault((pid, _key(bhk)), [0, None])
        cur[0] += n
        if lo is not None and (cur[1] is None or lo < cur[1]):
            cur[1] = lo

    societies = []
    for p in projects:
        pick = picks.get(p.id) or {}
        societies.append({"id": str(p.id), "name": p.name, "subtitle": ", ".join(x for x in (p.locality or p.sector, p.city) if x),
                          "sizes": [{"label": z["label"], "area_sqft": z.get("area_sqft"), "has_floor_plan": bool(z.get("floor_plan_file_id"))} for z in (p.sizes or []) if z.get("label")],
                          "chosen_sizes": [z["label"] for z in _chosen_sizes(p, pick.get("sizes"))]})

    def num(v):
        return float(v) if v is not None else None

    def stage(p: Project):
        s = STAGES.get(p.stage, p.stage)
        return f"{s}, possession {p.possession_date:%b %Y}" if p.possession_date and p.stage != "ready" else s

    def price_range(pid):
        lo, hi, _ = prices.get(pid, (None, None, None))
        if lo is None:
            return None
        return inr(lo) if lo == hi else f"{inr(lo)} – {inr(hi)}"

    summ = {p.id: inventory.summarize(counts.get(p.id, {})) for p in projects}
    spec: list[tuple] = [
        ("overview", "location", "Location", [", ".join(x for x in (p.sector, p.locality, p.city) if x) or None for p in projects], str, None),
        ("overview", "developer", "Developer", [p.developer for p in projects], str, None),
        ("overview", "stage", "Possession", [stage(p) for p in projects], str, None),
        ("overview", "rera", "RERA", [p.rera_id for p in projects], str, None),
        ("overview", "kind", "Type", [PROJECT_KINDS.get(p.kind, p.kind) for p in projects] if len({p.kind for p in projects}) > 1 or projects[0].kind != "residential" else [None] * len(projects), str, None),
        ("overview", "price", "Starting price", [num(prices.get(p.id, (None,))[0]) for p in projects], inr, "min"),
        ("overview", "range", "Price range", [price_range(p.id) for p in projects], str, None),
        ("overview", "rate", "Avg. price per sq ft", [num(prices.get(p.id, (None, None, None))[2]) for p in projects], lambda v: f"₹{_indian_digits(round(v))}", "min"),
        ("overview", "towers", "Towers", [towers.get(p.id) or None for p in projects], str, None),
        ("overview", "available", "Flats available", [summ[p.id]["available"] if summ[p.id]["total"] else None for p in projects], lambda v: f"{v}", "max"),
        ("overview", "total", "Total flats", [summ[p.id]["total"] or None for p in projects], str, None),
    ]

    # one row per layout the broker kept, lined up by size name across societies
    chosen = [_chosen_sizes(p, (picks.get(p.id) or {}).get("sizes")) for p in projects]
    def shown(z, zs):
        """A project with two sizes of the same name (two kinds of office) tells them apart by area."""
        dup = sum(_key(y["label"]) == _key(z["label"]) for y in zs) > 1
        return f"{z['label']} ({_indian_digits(round(z['area_sqft']))} sq ft)" if dup and z.get("area_sqft") else z["label"]

    labels: dict[str, str] = {}
    for zs in chosen:
        for z in zs:
            labels.setdefault(_key(shown(z, zs)), shown(z, zs))
    for k, label in labels.items():
        values = []
        for p, zs in zip(projects, chosen):
            z = next((z for z in zs if _key(shown(z, zs)) == k), None)
            if z is None:
                values.append(None)
                continue
            n, lo = by_size.get((p.id, _key(z["label"])), (0, None))
            bits = [f"{_indian_digits(round(z['area_sqft']))} sq ft" if z.get("area_sqft") else None, f"from {inr(lo)}" if lo is not None else None,
                    f"{n} available" if n else "None available right now", "with floor plan" if z.get("floor_plan_file_id") else None]
            values.append(" · ".join(b for b in bits if b))
        spec.append(("layouts", f"size:{k}", label, values, str, None))

    amen = {}
    for p in projects:
        for a in p.amenities or []:
            amen.setdefault(a.strip().lower(), a.strip())
    if amen:
        have = [{a.strip().lower() for a in p.amenities or []} for p in projects]
        spec.append(("amenities", "amenity_count", "Amenities listed", [len(h) or None for h in have], lambda v: f"{v}", "max"))
        # amenities most societies share first, so the differences sit together at the bottom
        order = sorted(amen, key=lambda a: (-sum(a in h for h in have), amen[a].lower()))[:MAX_AMENITY_ROWS]
        for a in order:
            spec.append(("amenities", f"amenity:{a}", amen[a], ["Yes" if a in h else "No" for h in have], str, None))

    rows = []
    for group, key, label, values, fmt, best in spec:
        if all(v is None or v == "" for v in values):
            continue
        present = [v for v in values if v is not None]
        winners: list[int] = []
        if best and len(present) >= 2 and len(set(present)) > 1:
            target = min(present) if best == "min" else max(present)
            winners = [i for i, v in enumerate(values) if v == target]
        texts = [fmt(v) if v is not None and v != "" else "—" for v in values]
        rows.append({"group": group, "key": key, "label": label, "values": texts, "best": winners, "same": len(set(texts)) == 1})
    return {"societies": societies, "rows": rows}


# ---- what goes into the PDF -------------------------------------------------------------------------------------------

def attachments(projects: list[Project], picks: dict[uuid.UUID, dict]) -> dict[uuid.UUID, dict]:
    """For each society: the photos, floor plans (with their size) and brochure the broker ticked. Ids that aren't this
    project's files are skipped, so a photo deleted since the page loaded doesn't break the send."""
    files = db.session.query(FileAsset).filter(FileAsset.project_id.in_([p.id for p in projects]), FileAsset.unit_id.is_(None), FileAsset.deleted_at.is_(None),
                                               FileAsset.doc_kind.in_(("brochure", "photo", "floor_plan"))).order_by(FileAsset.created_at).all()
    out = {}
    for p in projects:
        pick = picks.get(p.id) or {}
        mine = [f for f in files if f.project_id == p.id]
        by_id = {f.id: f for f in mine}
        want = list(dict.fromkeys(pick.get("photo_ids") or []))
        photos = [by_id[i] for i in want if i in by_id and by_id[i].doc_kind == "photo"][: inventory.MAX_PROJECT_PHOTOS]
        plans = []
        for z in _chosen_sizes(p, pick.get("sizes")):
            fid = z.get("floor_plan_file_id")
            f = by_id.get(uuid.UUID(fid)) if fid else None
            if f is not None and f.doc_kind == "floor_plan":
                plans.append((z, f))
        brochures = [f for f in mine if f.doc_kind == "brochure"]
        out[p.id] = {"photos": photos, "plans": plans, "brochure": brochures[-1] if pick.get("brochure") and brochures else None}
    return out


def render_pdf(data: dict, extras: dict[uuid.UUID, dict], projects: list[Project], *, title: str, client_name: str | None, prepared_by: str,
               workspace_name: str, note: str | None = None) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = _fonts()
    ink, muted, brand, line, good, band = (colors.HexColor(c) for c in ("#0f172a", "#64748b", "#4f46e5", "#e2e8f0", "#15803d", "#eef2ff"))
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=20, leading=24, textColor=ink),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=16, leading=20, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=10, leading=14, textColor=muted),
        "head": ParagraphStyle("h", fontName=bold, fontSize=11, leading=14, textColor=colors.white),
        "group": ParagraphStyle("g", fontName=bold, fontSize=8.5, leading=11, textColor=brand),
        "label": ParagraphStyle("l", fontName=regular, fontSize=9, leading=12, textColor=muted),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=9.5, leading=12.5, textColor=ink),
        "no": ParagraphStyle("n", fontName=regular, fontSize=9.5, leading=12.5, textColor=colors.HexColor("#94a3b8")),
        "best": ParagraphStyle("b", fontName=bold, fontSize=9.5, leading=12.5, textColor=good),
        "caption": ParagraphStyle("cap", fontName=regular, fontSize=9, leading=12, textColor=muted),
        "foot": ParagraphStyle("f", fontName=regular, fontSize=8, leading=11, textColor=muted),
    }
    page = landscape(A4)
    margin = 30
    today = dt.date.today().strftime("%d %b %Y")
    st_store = storage.get_storage()

    def chunk(els) -> bytes:
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin, title=title, author=prepared_by).build(els)
        return buf.getvalue()

    def read(f: FileAsset) -> bytes | None:
        try:
            return st_store.read(f.storage_key)
        except Exception:  # a file missing from storage shouldn't stop the whole PDF
            log.warning("comparison: couldn't read file %s", f.id, exc_info=True)
            return None

    def picture(raw: bytes, max_w: float, max_h: float):
        try:
            w, h = ImageReader(io.BytesIO(raw)).getSize()
        except Exception:
            return None
        s = min(max_w / w, max_h / h)
        return Image(io.BytesIO(raw), width=w * s, height=h * s)

    # 1. the table
    socs, rows = data["societies"], data["rows"]
    n = len(socs)
    els = [Paragraph(escape(title), st["title"]), Spacer(1, 4),
           Paragraph(escape(" · ".join(x for x in (f"Prepared for {client_name}" if client_name else None, f"by {prepared_by}, {workspace_name}", today) if x)), st["sub"])]
    if note:
        els += [Spacer(1, 8), Paragraph(escape(note).replace("\n", "<br/>"), st["cell"])]
    els.append(Spacer(1, 14))
    label_w = 130
    col_w = (page[0] - 2 * margin - label_w) / max(n, 1)
    table = [[Paragraph("", st["label"])] + [Paragraph(f"{escape(s['name'])}<br/><font size=8 color='#c7d2fe'>{escape(s['subtitle'])}</font>", st["head"]) for s in socs]]
    styles = [("BACKGROUND", (1, 0), (-1, 0), brand), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.5, line),
              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
              ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, 0), (-1, 0), 9)]
    groups = {"layouts": "LAYOUTS", "amenities": "AMENITIES"}
    last = "overview"
    for r in rows:
        if r["group"] != last and r["group"] in groups:
            table.append([Paragraph(groups[r["group"]], st["group"])] + [""] * n)
            styles += [("SPAN", (0, len(table) - 1), (-1, len(table) - 1)), ("BACKGROUND", (0, len(table) - 1), (-1, len(table) - 1), band), ("TOPPADDING", (0, len(table) - 1), (-1, len(table) - 1), 6)]
            last = r["group"]
        cells = [Paragraph(escape(r["label"]), st["label"])]
        for i, v in enumerate(r["values"]):
            if i in r["best"]:
                cells.append(Paragraph(escape(v) + " ✓", st["best"]))
            elif r["group"] == "amenities" and v in ("Yes", "No") and r["key"] != "amenity_count":
                cells.append(Paragraph("✓" if v == "Yes" else "—", st["best"] if v == "Yes" else st["no"]))
            else:
                cells.append(Paragraph(escape(v), st["cell"]))
        table.append(cells)
    t = Table(table, colWidths=[label_w] + [col_w] * n, repeatRows=1)
    t.setStyle(TableStyle(styles))
    sent = [p.name for p in projects if (x := extras.get(p.id)) and (x["photos"] or x["plans"] or x["brochure"])]
    els += [t, Spacer(1, 10), Paragraph("✓ marks the lowest starting price and rate, and the most flats available and amenities. Prices and availability are as of "
                                        + today + " and can change; please confirm before booking." + (" Photos, floor plans and brochures follow on the next pages." if sent else ""), st["foot"])]
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(chunk(els))))

    def append_pdf(raw: bytes | None, what: str):
        if not raw:
            return
        try:
            writer.append(PdfReader(io.BytesIO(raw)))
        except Exception:
            log.warning("comparison: skipped a %s that isn't a readable PDF", what, exc_info=True)

    # 2. per society: photos and image floor plans, then PDF floor plans and the brochure as they are
    body_w, body_h = page[0] - 2 * margin, page[1] - 2 * margin
    for p in projects:
        x = extras.get(p.id)
        if not x or not (x["photos"] or x["plans"] or x["brochure"]):
            continue
        els = [Paragraph(escape(p.name), st["h2"]), Paragraph(escape(" · ".join(b for b in (", ".join(y for y in (p.sector, p.locality, p.city) if y), f"RERA {p.rera_id}" if p.rera_id else None) if b)), st["sub"]), Spacer(1, 10)]
        photos = [im for f in x["photos"] if (raw := read(f)) and (im := picture(raw, (body_w - 12) / 2, (body_h - 80) / 2 - 8))]
        if photos:
            grid = [photos[i:i + 2] + [""] * (2 - len(photos[i:i + 2])) for i in range(0, len(photos), 2)]
            pt = Table(grid, colWidths=[body_w / 2] * 2)
            pt.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            els.append(pt)
        pdf_plans = []
        for z, f in x["plans"]:
            if f.mime_type == "application/pdf":
                pdf_plans.append((z, f))
                continue
            im = (raw := read(f)) and picture(raw, body_w, body_h - 60)
            if im:
                cap = " · ".join(b for b in (z["label"], f"{_indian_digits(round(z['area_sqft']))} sq ft" if z.get("area_sqft") else None) if b)
                # the first plan shares the society's opening page when there are no photos above it
                els += ([PageBreak(), Paragraph(escape(f"{p.name} · Floor plan"), st["h2"])] if len(els) > 3 else []) + [Paragraph(escape(cap), st["caption"]), Spacer(1, 8), im]
        if pdf_plans or x["brochure"]:
            later = [f"{z['label']} floor plan" for z, _ in pdf_plans] + (["brochure"] if x["brochure"] else [])
            els += [Spacer(1, 10), Paragraph(escape("Next pages: " + ", ".join(later) + "."), st["caption"])]
        writer.append(PdfReader(io.BytesIO(chunk(els))))
        for z, f in pdf_plans:
            append_pdf(read(f), "floor plan")
        if x["brochure"]:
            append_pdf(read(x["brochure"]), "brochure")

    writer.add_metadata({"/Title": title, "/Author": prepared_by})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def filename(data: dict) -> str:
    names = " vs ".join(s["name"] for s in data["societies"])[:80]
    return f"Society comparison {names}.pdf".replace("/", "-")
