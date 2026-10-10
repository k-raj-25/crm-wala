"""Explainable, deterministic lead scoring + deal probability + health signals (works with no LLM)."""
from __future__ import annotations

import datetime as dt

from app.models import Deal, Lead
from app.models.base import utcnow

FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me", "protonmail.com", "aol.com", "rediffmail.com", "live.com"}
SOURCE_POINTS = {"referral": 15, "website": 12, "demo_request": 15, "pricing_page": 12, "event": 8, "linkedin": 6, "webinar": 8, "ads": 5, "cold_outreach": 1, "import": 2,
                 "walk_in": 15, "99acres": 10, "magicbricks": 10, "housing": 10, "facebook_ads": 6, "instagram": 6, "site_visit": 15}
STATUS_POINTS = {"qualified": 15, "contacted": 5, "unqualified": -30, "lost": -20, "converted": 10}


def _title_points(title: str | None) -> int:
    t = (title or "").lower()
    if any(k in t for k in ("founder", "owner", "ceo", "cto", "cfo", "coo", "chief", "president", "managing director")):
        return 20
    if any(k in t for k in ("vp", "vice president", "director", "head of")):
        return 15
    if "manager" in t or "lead" in t:
        return 8
    return 2 if t else 0


def score_lead(lead: Lead, recent_activity_count: int = 0) -> tuple[int, list[dict]]:
    reasons: list[dict] = []

    def add(label: str, pts: int):
        if pts:
            reasons.append({"label": label, "points": pts})

    add("Baseline", 10)
    if lead.email:
        domain = lead.email.rsplit("@", 1)[-1].lower()
        add("Business email" if domain not in FREE_MAIL else "Personal email", 15 if domain not in FREE_MAIL else 5)
    add("Phone number provided", 5 if lead.phone else 0)
    add("Company provided", 5 if lead.company_name else 0)
    add("Decision-maker job title", _title_points(lead.job_title))
    add(f"High-intent source ({lead.source})" if lead.source else "Source", SOURCE_POINTS.get((lead.source or "").lower(), 0))
    add("Budget shared", 10 if (lead.budget_max or lead.budget_min) else 0)
    add("Knows what they're looking for", 8 if lead.intent else 0)
    add("Specific home size", 4 if lead.bhk else 0)
    add("Interested in a specific project or flat", 10 if (lead.unit_id or lead.project_id) else 0)
    add("Recent engagement", min(recent_activity_count * 4, 20))
    add(f"Status: {lead.status}", STATUS_POINTS.get(lead.status, 0))
    total = max(0, min(100, sum(r["points"] for r in reasons)))
    return total, reasons


def deal_probability(deal: Deal, now: dt.datetime | None = None) -> tuple[int, list[str]]:
    now = now or utcnow()
    if deal.status == "won":
        return 100, ["Deal is won"]
    if deal.status == "lost":
        return 0, ["Deal is lost"]
    base = deal.stage.probability if deal.stage else deal.probability
    notes = [f"Stage default: {base}%"]
    p = base
    if deal.last_activity_at and (now - deal.last_activity_at).days > 14:
        p -= 10
        notes.append("No activity for over 14 days (-10)")
    elif deal.last_activity_at and (now - deal.last_activity_at).days <= 3:
        p += 5
        notes.append("Recent activity (+5)")
    if deal.expected_close_date and deal.expected_close_date < now.date():
        p -= 10
        notes.append("Expected close date has passed (-10)")
    if deal.lead_score >= 70:
        p += 5
        notes.append("High lead score (+5)")
    return max(1, min(99, p)), notes
