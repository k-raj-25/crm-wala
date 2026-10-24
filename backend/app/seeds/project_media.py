"""Sample project details for demos and empty projects: society photos, a brochure, sizes with floor plans, RERA and amenities.

Everything is drawn here (no image files ship with the app): photos are simple PNG skylines, the brochure and floor plans are
PDFs drawn with reportlab. `fill_project` only fills what a project is missing, so it is safe to run again.
"""
from __future__ import annotations

import io
import random
import struct
import zlib

from sqlalchemy import func

from app.extensions import db
from app.models import FileAsset, Project, Unit
from app.services import storage

RESIDENTIAL_AMENITIES = ["Clubhouse", "Swimming pool", "Gym", "Kids' play area", "Landscaped garden", "Jogging track", "24x7 security", "Power backup", "Covered parking"]
COMMERCIAL_AMENITIES = ["Food court", "High-speed lifts", "Power backup", "24x7 security", "Visitor parking", "Central air conditioning", "Conference rooms"]
DEFAULT_SIZES = [("2 BHK", 1250), ("3 BHK", 1800), ("4 BHK", 2450)]
SCENES = ["Elevation", "Entrance", "Clubhouse", "Swimming pool", "Landscaped garden", "Night view"]
SKIES = {  # top colour, bottom colour
    "day": ((112, 165, 228), (214, 232, 248)), "dusk": ((52, 66, 128), (246, 168, 112)), "night": ((14, 20, 48), (52, 60, 110)), "morning": ((150, 196, 240), (250, 222, 190)),
}


# ---- PNG drawing -----------------------------------------------------------------------------------------------------

class _Canvas:
    """A tiny RGB canvas: rows of bytes, filled a span at a time so drawing stays fast in pure Python."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.rows = [bytearray(w * 3) for _ in range(h)]

    def span(self, y: int, x0: int, x1: int, c: tuple[int, int, int]) -> None:
        if 0 <= y < self.h:
            x0, x1 = max(0, int(x0)), min(self.w, int(x1))
            if x1 > x0:
                self.rows[y][x0 * 3:x1 * 3] = bytes(c) * (x1 - x0)

    def rect(self, x0, y0, x1, y1, c) -> None:
        for y in range(max(0, int(y0)), min(self.h, int(y1))):
            self.span(y, x0, x1, c)

    def ellipse(self, cx, cy, rx, ry, c) -> None:
        for y in range(int(cy - ry), int(cy + ry) + 1):
            d = 1 - ((y - cy) / ry) ** 2
            if d > 0:
                half = rx * d ** 0.5
                self.span(y, cx - half, cx + half, c)

    def gradient(self, y0, y1, top, bottom) -> None:
        for y in range(int(y0), int(y1)):
            t = (y - y0) / max(1, y1 - y0)
            self.span(y, 0, self.w, tuple(int(top[k] * (1 - t) + bottom[k] * t) for k in range(3)))

    def png(self) -> bytes:
        raw = b"".join(b"\x00" + bytes(r) for r in self.rows)
        chunk = lambda tag, data: struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)  # noqa: E731
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def society_photo(scene: str, rnd: random.Random, w: int = 960, h: int = 640) -> bytes:
    """A stylised photo of the society: sky, towers with lit windows, and something in front that fits the scene."""
    night = scene == "Night view"
    sky = SKIES["night" if night else rnd.choice(["day", "dusk", "morning"])]
    cv = _Canvas(w, h)
    ground = int(h * 0.8)
    cv.gradient(0, ground, *sky)
    if night:
        for _ in range(60):
            cv.rect(*(lambda x, y: (x, y, x + 2, y + 2))(rnd.randint(0, w), rnd.randint(0, ground // 2)), (230, 230, 255))
        cv.ellipse(w * 0.82, h * 0.14, 26, 26, (246, 240, 210))
    else:
        cv.ellipse(w * rnd.uniform(0.6, 0.9), h * 0.16, 34, 34, (255, 236, 180))
    body = (40, 46, 70) if night else rnd.choice([(84, 96, 122), (128, 112, 104), (96, 110, 128), (150, 140, 128)])
    lit, dark = (255, 214, 120), (_shade(body, 0.6) if night else (160, 190, 220))
    n = rnd.randint(3, 5)
    slot = w / n
    for i in range(n):
        tw = slot * rnd.uniform(0.5, 0.7)
        x0 = i * slot + (slot - tw) / 2
        top = int(h * rnd.uniform(0.12, 0.42))
        c = _shade(body, rnd.uniform(0.85, 1.15))
        cv.rect(x0, top, x0 + tw, ground, c)
        cv.rect(x0 - 4, top - 8, x0 + tw + 4, top, _shade(c, 0.8))  # parapet
        cols = max(3, int(tw // 30))
        for y in range(top + 16, ground - 24, 30):
            for k in range(cols):
                wx = x0 + 10 + k * (tw - 20) / cols
                cv.rect(wx, y, wx + (tw - 20) / cols - 8, y + 16, lit if rnd.random() < (0.55 if night else 0.18) else dark)
    grass = (44, 70, 46) if night else (88, 146, 84)
    cv.rect(0, ground, w, h, grass)
    if scene == "Swimming pool":
        cv.ellipse(w / 2, ground + (h - ground) * 0.55, w * 0.34, (h - ground) * 0.36, (238, 232, 216))
        cv.ellipse(w / 2, ground + (h - ground) * 0.55, w * 0.31, (h - ground) * 0.28, (64, 176, 222))
    elif scene == "Entrance":
        cv.rect(w * 0.42, ground - 70, w * 0.58, ground, (60, 60, 64))
        cv.rect(w * 0.4, ground - 84, w * 0.6, ground - 70, (190, 160, 110))
        cv.rect(w * 0.45, ground, w * 0.55, h, (176, 168, 156))
    elif scene == "Clubhouse":
        cv.rect(w * 0.25, ground - 90, w * 0.75, ground, (236, 228, 214))
        cv.rect(w * 0.22, ground - 104, w * 0.78, ground - 90, (150, 90, 70))
        for k in range(6):
            cv.rect(w * 0.29 + k * w * 0.075, ground - 70, w * 0.29 + k * w * 0.075 + 30, ground - 20, (120, 170, 200))
    if scene in ("Landscaped garden", "Clubhouse", "Entrance", "Elevation"):
        for k in range(rnd.randint(4, 8)):
            tx = rnd.uniform(0, w)
            cv.rect(tx - 4, ground - 10, tx + 4, ground + 30, (96, 70, 50))
            cv.ellipse(tx, ground - 24, 28, 30, (46, 120, 60) if k % 2 else (62, 140, 70))
    return cv.png()


# ---- PDFs ------------------------------------------------------------------------------------------------------------

def floor_plan_pdf(project: Project, label: str, area: float | None) -> bytes:
    """A simple architect-style floor plan for one size: rooms with names and approximate dimensions."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"{project.name} — {label} floor plan")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, H - 50, f"{project.name} · {label}")
    c.setFont("Helvetica", 11)
    c.drawString(40, H - 70, f"{f'{int(area):,} sq ft super area · ' if area else ''}Sample floor plan for illustration")
    beds = next((int(ch) for ch in label if ch.isdigit()), 0)
    rooms = [("Living / Dining", 2, 1), ("Kitchen", 1, 1)] + [(("Master bedroom" if i == 0 else f"Bedroom {i + 1}"), 1, 1) for i in range(beds)] + [("Balcony", 1, 1)]
    if not beds:
        rooms = [("Open workspace", 3, 1), ("Cabin", 1, 1), ("Meeting room", 1, 1), ("Pantry", 1, 1), ("Washroom", 1, 1)]
    cols = 4
    rooms = rooms[:7] + [("Balcony", 1, 1)] if len(rooms) > 8 else rooms
    rooms += [(name, 1, 1) for name in ("Toilet", "Utility", "Store")][:max(0, 2 * cols - sum(r[1] for r in rooms))]
    x0, y0, cw, ch = 60, 90, (W - 120) / cols, (H - 200) / 2
    c.setLineWidth(3)
    c.rect(x0, y0, cw * cols, ch * 2)
    c.setLineWidth(1.5)
    col, row = 0, 1
    for name, span, _ in rooms:
        if col + span > cols:
            col, row = 0, row - 1
        if row < 0:
            break
        x, y = x0 + col * cw, y0 + row * ch
        c.rect(x, y, cw * span, ch)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + cw * span / 2, y + ch / 2 + 6, name.upper())
        c.setFont("Helvetica", 9)
        c.drawCentredString(x + cw * span / 2, y + ch / 2 - 10, f"{11 * span + 2}'0\" x 12'6\"")
        c.line(x + 30, y, x + 60, y + 18)  # door swing
        col += span
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 30, "Dimensions are indicative. Sample document generated by CRM Wala.")
    c.showPage()
    c.save()
    return buf.getvalue()


def brochure_pdf(project: Project, sizes: list[dict]) -> bytes:
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{project.name} brochure")
    c.setFillColor(HexColor("#1e2a4a"))
    c.rect(0, H - 300, W, 300, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 34)
    c.drawString(48, H - 140, project.name)
    c.setFont("Helvetica", 15)
    c.drawString(48, H - 170, " · ".join(x for x in (project.developer and f"by {project.developer}", project.sector, project.city) if x))
    if project.rera_id:
        c.setFont("Helvetica", 10)
        c.drawString(48, H - 270, f"RERA No. {project.rera_id}")
    c.setFillColor(HexColor("#111827"))
    y = H - 350
    c.setFont("Helvetica-Bold", 16)
    c.drawString(48, y, "Sizes on offer")
    c.setFont("Helvetica", 12)
    for z in sizes:
        y -= 22
        c.drawString(60, y, f"• {z['label']}" + (f" — {int(z['area_sqft']):,} sq ft" if z.get("area_sqft") else ""))
    y -= 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(48, y, "Amenities")
    c.setFont("Helvetica", 12)
    for i, a in enumerate(project.amenities or []):
        c.drawString(60 + (i % 2) * 240, y - 22 * (i // 2 + 1), f"• {a}")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(48, 30, "Sample brochure generated by CRM Wala for demonstration.")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---- filling a project -----------------------------------------------------------------------------------------------

def _store(project: Project, filename: str, mime: str, data: bytes, doc_kind: str, user_id) -> FileAsset:
    key = storage.new_key(project.workspace_id, filename)
    storage.get_storage().put(key, io.BytesIO(data), mime)
    fa = FileAsset(workspace_id=project.workspace_id, project_id=project.id, filename=filename, storage_key=key, mime_type=mime,
                   size_bytes=len(data), uploaded_by=user_id, doc_kind=doc_kind)
    db.session.add(fa)
    db.session.flush()
    return fa


def _sizes_from_units(project: Project) -> list[tuple[str, float | None]]:
    """One size per BHK (average area); offices, shops and plots without a BHK get one size per distinct area."""
    rows = db.session.query(Unit.bhk, Unit.kind, Unit.area_sqft).filter(Unit.project_id == project.id, Unit.deleted_at.is_(None)).distinct().all()
    groups: dict[str, list[float]] = {}
    for bhk, kind, area in rows:
        label = bhk or (f"{kind.title()} · {int(area):,} sq ft" if area else kind.title())
        groups.setdefault(label, []).extend([float(area)] if area else [])
    out = [(label.split(" · ")[0], round(sum(a) / len(a), -1) if a else None) for label, a in groups.items()]
    out.sort(key=lambda x: (x[1] or 0))
    return out[:6] or ([] if project.kind == "commercial" else DEFAULT_SIZES)


def fill_project(project: Project, user_id=None, rnd: random.Random | None = None, photos: int = 6) -> list[str]:
    """Add whatever sample details the project is missing. Returns what was added."""
    rnd = rnd or random.Random(str(project.id))
    added: list[str] = []
    slug = "".join(ch if ch.isalnum() else "-" for ch in project.name.lower()).strip("-")[:40] or "project"
    if not project.rera_id:
        project.rera_id = f"RC/REP/HARERA/GGM/{rnd.randint(2021, 2025)}/{rnd.randint(100, 999)}"
        added.append("RERA")
    if not project.amenities:
        pool = COMMERCIAL_AMENITIES if project.kind == "commercial" else RESIDENTIAL_AMENITIES
        project.amenities = rnd.sample(pool, k=min(6, len(pool)))
        added.append("amenities")
    if not project.sizes:
        sizes = [{"label": label, "area_sqft": area, "floor_plan_file_id": None} for label, area in _sizes_from_units(project) or [("Office", 1000.0)]]
        for i, z in enumerate(sizes):
            fname = f"{slug}-{''.join(ch if ch.isalnum() else '-' for ch in z['label'].lower())}-{i + 1}-floor-plan.pdf"
            z["floor_plan_file_id"] = str(_store(project, fname, "application/pdf", floor_plan_pdf(project, z["label"], z["area_sqft"]), "floor_plan", user_id).id)
        project.sizes = sizes
        added.append(f"{len(sizes)} sizes with floor plans")
    q = db.session.query(FileAsset).filter(FileAsset.project_id == project.id, FileAsset.unit_id.is_(None), FileAsset.deleted_at.is_(None))
    if not q.filter(FileAsset.doc_kind == "photo").first():
        for i, scene in enumerate(SCENES[:photos]):
            _store(project, f"{slug}-{i + 1}-{scene.lower().replace(' ', '-')}.png", "image/png", society_photo(scene, rnd), "photo", user_id)
        added.append(f"{min(photos, len(SCENES))} photos")
    if not q.filter(FileAsset.doc_kind == "brochure").first():
        _store(project, f"{slug}-brochure.pdf", "application/pdf", brochure_pdf(project, project.sizes), "brochure", user_id)
        added.append("brochure")
    return added
