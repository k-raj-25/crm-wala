"""Dashboard + Reports + saved reports."""
from __future__ import annotations

import csv
import datetime as dt
import io

from flask import Blueprint, Response, g, request
from pydantic import Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.auth import protect, require
from app.core.crud import parse_date
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import SavedReport
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import audit, reporting

bp = Blueprint("analytics", __name__, url_prefix="/api/v1")


def _range() -> tuple[dt.datetime, dt.datetime]:
    a = request.args
    end = parse_date(a.get("to"), end=True) or utcnow()
    start = parse_date(a.get("from")) or reporting.day_start(end - dt.timedelta(days=int(a.get("days", 30)) - 1))
    if start > end:
        raise bad_request("Start date must be before end date")
    if (end - start).days > 800:
        raise bad_request("Choose a range of up to ~2 years")
    return start, end


@bp.get("/dashboard")
@protect("reports.read")
def dashboard():
    ws = g.workspace.id
    start, end = _range()
    bucket = reporting.bucket_for(start, end)
    mine = request.args.get("scope") == "mine"
    owner = g.user.id if mine else None
    try:
        pid = request.args.get("pipeline_id")
        return ok({
            "range": {"from": start.isoformat(), "to": end.isoformat(), "bucket": bucket},
            "metrics": reporting.headline_metrics(ws, start, end),
            "revenue_series": reporting.revenue_series(ws, start, end, bucket, owner),
            "pipeline_by_stage": reporting.pipeline_by_stage(ws, pid),
            "lead_funnel": reporting.lead_funnel(ws, start, end),
            "sales_funnel": reporting.sales_funnel(ws, start, end),
            "deal_velocity": reporting.deal_velocity(ws, start, end, bucket),
            "forecast": reporting.forecast(ws),
            "activity_feed": reporting.activity_feed(ws) if "activities.read" in g.permissions or "*" in g.permissions else [],
            "focus": reporting.todays_focus(ws, g.user.id),
        })
    except ApiError:
        raise


@bp.get("/dashboard/focus")
@protect("reports.read")
def focus():
    return ok(reporting.todays_focus(g.workspace.id, g.user.id if request.args.get("scope") != "all" else None))


@bp.get("/reports")
@protect("reports.read")
def report_types():
    return ok([{"key": k, "label": v, "advanced": k in reporting.ADVANCED} for k, v in reporting.REPORT_TYPES.items()])


def _run(rtype: str) -> dict:
    if rtype not in reporting.REPORT_TYPES:
        raise not_found("Report")
    if rtype in reporting.ADVANCED and "advanced_reports" not in g.features:
        raise ApiError(402, "feature_unavailable", "Advanced reports are available on Growth and above.", {"feature": "advanced_reports"})
    start, end = _range()
    return {**reporting.run_report(rtype, start, end, request.args.get("owner_id"), request.args.get("pipeline_id")),
            "range": {"from": start.isoformat(), "to": end.isoformat()}, "type": rtype}


@bp.get("/reports/<rtype>")
@protect("reports.read")
def run(rtype):
    return ok(_run(rtype))


def _fmt(v, kind):
    if v is None:
        return ""
    if kind == "currency":
        return f"{float(v):,.2f}"
    if kind == "percent":
        return f"{v}%"
    return v


@bp.get("/reports/<rtype>/export.csv")
@protect("data.export", allow_restricted=True)
def export_csv(rtype):
    require("reports.read")
    r = _run(rtype)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c["label"] for c in r["columns"]])
    for row in r["rows"]:
        w.writerow([row.get(c["key"], "") for c in r["columns"]])
    audit.record("report.exported", entity_type="report", summary=f"Exported {rtype} report (CSV)")
    db.session.commit()
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{rtype}-report.csv"'})


def render_pdf(r: dict, workspace_name: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=32, title=r["title"])
    st = getSampleStyleSheet()
    els = [Paragraph(f"{r['title']} report", st["Title"]), Paragraph(f"{workspace_name} · {r['range']['from'][:10]} → {r['range']['to'][:10]}", st["Normal"]), Spacer(1, 12)]
    if r.get("summary"):
        els.append(Table([[s["label"] for s in r["summary"]], [str(_fmt(s["value"], s["format"])) for s in r["summary"]]],
                         style=TableStyle([("FONTSIZE", (0, 0), (-1, 0), 8), ("TEXTCOLOR", (0, 0), (-1, 0), colors.grey), ("FONTSIZE", (0, 1), (-1, 1), 14)])))
        els.append(Spacer(1, 14))
    data = [[c["label"] for c in r["columns"]]] + [[str(_fmt(row.get(c["key"]), c["type"])) for c in r["columns"]] for row in r["rows"][:200]]
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0"))]))
    els.append(t)
    doc.build(els)
    return buf.getvalue()


@bp.get("/reports/<rtype>/export.pdf")
@protect("data.export", allow_restricted=True)
def export_pdf(rtype):
    require("reports.read")
    r = _run(rtype)
    audit.record("report.exported", entity_type="report", summary=f"Exported {rtype} report (PDF)")
    db.session.commit()
    return Response(render_pdf(r, g.workspace.name), mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{rtype}-report.pdf"'})


class SavedReportIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    report_type: str
    params: dict = Field(default_factory=dict)
    schedule: str | None = Field(default=None, pattern="^(daily|weekly|monthly)$")
    recipients: list[Email] = Field(default_factory=list, max_length=10)


@bp.get("/saved-reports")
@protect("reports.read")
def list_saved():
    rows = db.session.query(SavedReport).filter_by(workspace_id=g.workspace.id).order_by(SavedReport.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.post("/saved-reports")
@protect("reports.manage")
def save_report():
    d = parse(SavedReportIn)
    if d.report_type not in reporting.REPORT_TYPES:
        raise ApiError(422, "validation_error", "Unknown report type", {"report_type": "Unknown"})
    r = SavedReport(workspace_id=g.workspace.id, owner_id=g.user.id, **d.model_dump())
    db.session.add(r)
    audit.record("report.saved", entity_type="report", entity_id=r.id, summary=f"Saved report “{r.name}”" + (f" (scheduled {r.schedule})" if r.schedule else ""))
    db.session.commit()
    return created(r.to_dict())


@bp.patch("/saved-reports/<uuid:rid>")
@protect("reports.manage")
def update_saved(rid):
    r = db.session.query(SavedReport).filter_by(id=rid, workspace_id=g.workspace.id).one_or_none()
    if r is None:
        raise not_found("Report")
    d = parse(SavedReportIn)
    for k, v in d.model_dump().items():
        setattr(r, k, v)
    db.session.commit()
    return ok(r.to_dict())


@bp.delete("/saved-reports/<uuid:rid>")
@protect("reports.manage")
def delete_saved(rid):
    r = db.session.query(SavedReport).filter_by(id=rid, workspace_id=g.workspace.id).one_or_none()
    if r is None:
        raise not_found("Report")
    db.session.delete(r)
    db.session.commit()
    return no_content()
