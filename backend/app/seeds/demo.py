"""Realistic demo data. Everything lives in ONE workspace flagged is_demo=true with @demo.crmwala.dev users,
so it can never mix with production tenants and can be wiped with `flask seed-demo --reset`."""
from __future__ import annotations

import datetime as dt
import random

from app.core.passwords import hash_password
from app.core.tenant import bypass_scope, tenant_scope
from app.extensions import db
from app.models import (
    Activity, Automation, Call, Company, Contact, CustomFieldDef, Deal, Email, Lead, Meeting, Note, Notification, Pipeline, PipelineStage,
    Role, Tag, Task, User, Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.services import scoring
from app.services.workspaces import DEFAULT_LEAD_STATUSES, create_workspace, seed_platform, system_role

PASSWORD = "Demo@12345"
SLUG = "acme-demo"

COMPANIES = [
    ("Zenith Logistics", "Logistics", "201-500", "Mumbai, IN", "zenithlogistics.in", 48_00_00_000), ("Bluepeak Software", "SaaS", "51-200", "Bengaluru, IN", "bluepeak.io", 12_00_00_000),
    ("Nimbus Retail", "Retail", "501-1000", "Delhi, IN", "nimbusretail.com", 150_00_00_000), ("Orbit Fintech", "Fintech", "51-200", "Pune, IN", "orbitfin.co", 22_00_00_000),
    ("GreenLeaf Organics", "Food & Beverage", "11-50", "Kochi, IN", "greenleaforganics.in", 6_00_00_000), ("Kavya Textiles", "Manufacturing", "201-500", "Surat, IN", "kavyatextiles.com", 60_00_00_000),
    ("Pixel & Pine Studio", "Design Agency", "11-50", "Goa, IN", "pixelpine.studio", 3_00_00_000), ("Atlas Realty", "Real Estate", "51-200", "Hyderabad, IN", "atlasrealty.in", 35_00_00_000),
    ("Vertex Health", "Healthcare", "201-500", "Chennai, IN", "vertexhealth.org", 80_00_00_000), ("Lumen Education", "Education", "51-200", "Jaipur, IN", "lumenedu.in", 9_00_00_000),
    ("Harborline Freight", "Logistics", "1001-5000", "Singapore, SG", "harborline.sg", 400_00_00_000), ("Saffron Hospitality", "Hospitality", "201-500", "Udaipur, IN", "saffronhotels.in", 28_00_00_000),
    ("Quantum Analytics", "Data & AI", "11-50", "Austin, US", "quantum-analytics.ai", 14_00_00_000), ("BrightPath Consulting", "Consulting", "11-50", "London, UK", "brightpath.co.uk", 5_00_00_000),
    ("Urban Nest Interiors", "Interior Design", "11-50", "Ahmedabad, IN", "urbannest.in", 4_00_00_000),
]
CONTACTS = [  # first, last, title, company index
    ("Rahul", "Khanna", "Head of Operations", 0), ("Ananya", "Iyer", "VP Engineering", 1), ("Karan", "Malhotra", "Procurement Lead", 2), ("Ishita", "Banerjee", "CFO", 3),
    ("Meera", "Nair", "Founder", 4), ("Suresh", "Patel", "Managing Director", 5), ("Zoya", "Fernandes", "Creative Director", 6), ("Aditya", "Reddy", "Sales Director", 7),
    ("Dr. Neha", "Gupta", "Chief of Staff", 8), ("Pranav", "Joshi", "Principal", 9), ("Wei", "Tan", "Regional Manager", 10), ("Kabir", "Singh", "General Manager", 11),
    ("Olivia", "Bennett", "CEO", 12), ("James", "Whitfield", "Partner", 13), ("Tara", "Shah", "Studio Owner", 14), ("Arjun", "Menon", "Product Manager", 1),
    ("Riya", "Kulkarni", "Finance Controller", 3), ("Dev", "Choudhary", "IT Head", 2), ("Sana", "Qureshi", "Marketing Lead", 7), ("Nikhil", "Verma", "Director of Supply Chain", 0),
]
LEADS = [
    ("Aarti", "Desai", "Founder", "Sparrow Wellness", "referral"), ("Mohit", "Agarwal", "CEO", "Cobalt Cycles", "website"), ("Fatima", "Sheikh", "Marketing Manager", "Rose & Co", "linkedin"),
    ("Gautam", "Bhatt", "Operations Head", "Indigo Freight", "event"), ("Lakshmi", "Pillai", "Director", "Coastal Ayurveda", "referral"), ("Harsh", "Vora", "Co-founder", "TinyTech Labs", "demo_request"),
    ("Simran", "Kaur", "Student", None, "ads"), ("Oliver", "Grant", "VP Sales", "Northwind Trading", "website"), ("Pooja", "Hegde", "Procurement Manager", "Metro Mart", "cold_outreach"),
    ("Yash", "Thakur", "Owner", "Thakur Motors", "website"), ("Isha", "Rastogi", "Head of Growth", "FreshBasket", "pricing_page"), ("Rohan", "Bose", "CTO", "Cloudnine Systems", "linkedin"),
    ("Tanvi", "Mishra", "Manager", "Bright Smiles Dental", "ads"), ("Farhan", "Ali", "Managing Partner", "Ali & Sons Exports", "referral"), ("Naina", "Saxena", "Founder", "Leaf & Loom", "event"),
    ("Siddharth", "Rao", "Director", "Rao Constructions", "website"), ("Kritika", "Jain", "Admin", None, "cold_outreach"), ("Victor", "D'Souza", "General Manager", "Goa Beach Resorts", "pricing_page"),
    ("Anjali", "Mukherjee", "Lead Designer", "Studio Mukherjee", "linkedin"), ("Bharat", "Solanki", "Chairman", "Solanki Group", "referral"), ("Divya", "Krishnan", "VP Product", "Pulse Health", "demo_request"),
    ("Eshan", "Kapoor", "Partner", "Kapoor Legal", "website"), ("Gita", "Venkat", "Principal", "Venkat Academy", "event"), ("Hrithik", "Sen", "Founder", "Sen Studios", "ads"),
    ("Jasmine", "Dhillon", "Owner", "Dhillon Dairy", "referral"), ("Kunal", "Tripathi", "Head of IT", "Tripathi Infra", "cold_outreach"), ("Leena", "George", "Director", "George Pharma", "website"),
    ("Manish", "Pandey", "Sales Manager", "Pandey Auto", "linkedin"), ("Nandini", "Roy", "CEO", "Roy Robotics", "demo_request"), ("Omkar", "Patil", "Consultant", "Patil Advisory", "pricing_page"),
]
STATUS_BY_IDX = ["new", "new", "contacted", "contacted", "qualified", "new", "unqualified", "qualified", "contacted", "new", "new", "qualified", "contacted", "contacted", "new",
                 "qualified", "lost", "new", "contacted", "new", "qualified", "new", "contacted", "new", "contacted", "unqualified", "new", "contacted", "qualified", "new"]
# (name, company idx, contact idx, value, stage name, owner idx, days-until-close, priority, source)
DEALS = [
    ("Zenith — Fleet CRM rollout", 0, 0, 18_50_000, "Negotiation", 0, 9, "high", "referral"), ("Bluepeak — Team licenses", 1, 1, 7_20_000, "Proposal", 1, 18, "medium", "website"),
    ("Nimbus — Store ops platform", 2, 2, 42_00_000, "Discovery", 0, 40, "high", "event"), ("Orbit — Compliance suite", 3, 3, 12_00_000, "Proposal", 2, 12, "high", "linkedin"),
    ("GreenLeaf — Starter plan", 4, 4, 1_20_000, "Qualified", 2, 25, "low", "website"), ("Kavya — Dealer network CRM", 5, 5, 26_00_000, "Negotiation", 1, 6, "urgent", "referral"),
    ("Pixel & Pine — Studio pack", 6, 6, 95_000, "Lead", 3, 30, "low", "ads"), ("Atlas — Realty pipeline", 7, 7, 9_80_000, "Discovery", 3, 22, "medium", "website"),
    ("Vertex — Patient outreach", 8, 8, 31_00_000, "Proposal", 0, 28, "high", "referral"), ("Lumen — Admissions CRM", 9, 9, 4_50_000, "Qualified", 1, 35, "medium", "event"),
    ("Harborline — APAC rollout", 10, 10, 85_00_000, "Discovery", 0, 75, "urgent", "linkedin"), ("Saffron — Guest CRM", 11, 11, 8_40_000, "Negotiation", 2, 3, "medium", "referral"),
    ("Quantum — Analytics add-on", 12, 12, 5_60_000, "Lead", 3, 50, "low", "website"), ("BrightPath — Advisory seats", 13, 13, 2_75_000, "Qualified", 1, 20, "medium", "linkedin"),
    ("Urban Nest — Pilot", 14, 14, 1_80_000, "Proposal", 2, 14, "medium", "referral"),
]
# historical closed deals: (name, company idx, value, status, days ago closed, owner idx)
HISTORY = [
    ("Zenith — Pilot", 0, 6_00_000, "won", 150, 0), ("Nimbus — Pilot", 2, 9_50_000, "won", 128, 1), ("Orbit — Onboarding", 3, 4_20_000, "won", 104, 2), ("Vertex — Phase 1", 8, 14_00_000, "won", 88, 0),
    ("Kavya — Pilot", 5, 5_50_000, "won", 70, 1), ("Saffron — Pilot", 11, 3_30_000, "won", 55, 2), ("Atlas — Starter", 7, 2_90_000, "won", 41, 3), ("Bluepeak — Pilot", 1, 3_80_000, "won", 29, 1),
    ("Lumen — Pilot", 9, 2_10_000, "won", 18, 0), ("Harborline — Trial", 10, 11_00_000, "won", 9, 0), ("Pixel & Pine — Retainer", 6, 1_20_000, "lost", 95, 3), ("Quantum — POC", 12, 4_00_000, "lost", 60, 3),
    ("GreenLeaf — Pilot", 4, 90_000, "lost", 33, 2), ("Urban Nest — Pilot", 14, 1_50_000, "lost", 14, 2),
]


def _wipe() -> None:
    with bypass_scope():
        ws = db.session.query(Workspace).filter_by(slug=SLUG).first()
        if ws:
            db.session.delete(ws)
        db.session.flush()
        db.session.query(User).filter(User.email.like("%@demo.crmwala.dev")).delete(synchronize_session=False)
        db.session.commit()


def seed_demo(reset: bool = False, plan: str = "trial") -> dict:
    rnd = random.Random(42)
    now = utcnow()
    with bypass_scope():
        seed_platform()
    if reset:
        _wipe()
    with bypass_scope():
        if db.session.query(Workspace).filter_by(slug=SLUG).first():
            return {"email": "demo@demo.crmwala.dev", "password": PASSWORD, "workspace": "Acme Demo (already exists — use --reset to recreate)", "counts": "unchanged"}
        pw = hash_password(PASSWORD)
        people = [("Aarav Mehta", "demo@demo.crmwala.dev", "owner"), ("Priya Sharma", "priya@demo.crmwala.dev", "manager"), ("Rohit Verma", "rohit@demo.crmwala.dev", "sales_rep"),
                  ("Sneha Kapoor", "sneha@demo.crmwala.dev", "sales_rep"), ("Vikram Rao", "vikram@demo.crmwala.dev", "viewer")]
        users: list[User] = []
        for name, email, _ in people:
            u = User(name=name, email=email, password_hash=pw, email_verified_at=now, last_login_at=now - dt.timedelta(hours=rnd.randint(1, 48)))
            db.session.add(u)
            users.append(u)
        db.session.flush()
        ws = create_workspace(users[0], "Acme Demo Co", company_size="11-50", industry="SaaS", is_demo=True)
        ws.slug, ws.sales_model, ws.goals = SLUG, "b2b", ["manage_leads", "track_deals", "analyze_revenue"]
        ws.onboarding_completed_at = now
        ws.trial_ends_at, ws.trial_started_at = now + dt.timedelta(days=2, hours=3), now - dt.timedelta(hours=21)
        if plan != "trial":
            ws.plan_key, ws.subscription_status, ws.billing_interval = plan, "active", "monthly"
            ws.current_period_end = now + dt.timedelta(days=21)
        for u, (_, _, role) in list(zip(users, people))[1:]:
            db.session.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role_id=system_role(role).id))
        db.session.flush()
        with tenant_scope(ws.id):
            pipeline = db.session.query(Pipeline).filter_by(workspace_id=ws.id).one()
            stages = {s.name: s for s in db.session.query(PipelineStage).filter_by(pipeline_id=pipeline.id)}
            for t, c in (("enterprise", "#6366f1"), ("hot", "#ef4444"), ("renewal", "#10b981"), ("partner", "#f59e0b"), ("web-form", "#0ea5e9")):
                db.session.add(Tag(workspace_id=ws.id, name=t, color=c))
            db.session.add(CustomFieldDef(workspace_id=ws.id, entity_type="contact", key="preferred_language", label="Preferred language", field_type="dropdown", options=["English", "Hindi", "Tamil", "Marathi"], position=0))
            db.session.add(CustomFieldDef(workspace_id=ws.id, entity_type="deal", key="contract_length_months", label="Contract length (months)", field_type="number", position=0))
            companies: list[Company] = []
            for name, ind, size, loc, site, rev in COMPANIES:
                c = Company(workspace_id=ws.id, name=name, industry=ind, size=size, location=loc, website=f"https://{site}", domain=site, annual_revenue=rev, owner_id=users[rnd.randint(0, 3)].id,
                            created_at=now - dt.timedelta(days=rnd.randint(30, 200)), tags=rnd.sample(["enterprise", "partner", "renewal"], k=rnd.randint(0, 1)))
                db.session.add(c)
                companies.append(c)
            db.session.flush()
            contacts: list[Contact] = []
            for first, last, title, ci in CONTACTS:
                email = f"{first.lower().replace('dr. ', '')}.{last.lower()}@{COMPANIES[ci][4]}"
                c = Contact(workspace_id=ws.id, first_name=first, last_name=last, email=email, phone=f"+91 9{rnd.randint(100000000, 999999999)}", job_title=title, company_id=companies[ci].id,
                            owner_id=users[rnd.randint(0, 3)].id, location=COMPANIES[ci][3], created_at=now - dt.timedelta(days=rnd.randint(5, 150)),
                            custom={"preferred_language": rnd.choice(["English", "Hindi"])}, socials={"linkedin": f"https://linkedin.com/in/{first.lower()}-{last.lower()}"},
                            last_contacted_at=now - dt.timedelta(days=rnd.randint(0, 30)))
                db.session.add(c)
                contacts.append(c)
            db.session.flush()
            for i, (first, last, title, comp, source) in enumerate(LEADS):
                status = STATUS_BY_IDX[i]
                contacted = None if status == "new" else now - dt.timedelta(days=rnd.choice([1, 2, 3, 5, 9, 12, 20]))
                lead = Lead(workspace_id=ws.id, first_name=first, last_name=last, email=f"{first.lower()}.{last.lower().replace(chr(39), '')}@{(comp or 'gmail').lower().replace(' ', '').replace('&', 'and')}{'.com' if comp else '.com'}",
                            phone=f"+91 8{rnd.randint(100000000, 999999999)}", company_name=comp, job_title=title, source=source, status=status, owner_id=users[i % 4].id,
                            created_at=now - dt.timedelta(days=rnd.randint(0, 45), hours=rnd.randint(0, 20)), last_contacted_at=contacted, location=rnd.choice(["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai", "Kolkata"]),
                            tags=(["hot"] if i % 7 == 0 else []) + (["web-form"] if source in ("website", "pricing_page", "demo_request") else []))
                if status in ("new", "contacted", "qualified"):
                    offset = rnd.choice([-3, -1, 0, 0, 1, 2, 5, None])
                    lead.next_follow_up_at = (now.replace(hour=11, minute=0) + dt.timedelta(days=offset)) if offset is not None else None
                lead.score, lead.score_reasons = scoring.score_lead(lead, rnd.randint(0, 3))
                db.session.add(lead)
                db.session.flush()
                db.session.add(Activity(workspace_id=ws.id, type="created", title="Lead created", lead_id=lead.id, user_id=lead.owner_id, occurred_at=lead.created_at, is_demo=True))
                if contacted:
                    db.session.add(Activity(workspace_id=ws.id, type="email", title="Email sent: Intro & next steps", lead_id=lead.id, user_id=lead.owner_id, occurred_at=contacted, is_demo=True))
                    lead.last_activity_at = contacted
            db.session.flush()

            def make_deal(name, ci, contact_i, value, stage, owner, status, created, closed=None, close_in=None, prio="medium", source="website"):
                st = stages[stage]
                d = Deal(workspace_id=ws.id, name=name, company_id=companies[ci].id, contact_id=contacts[contact_i].id if contact_i is not None else None, pipeline_id=pipeline.id, stage_id=st.id,
                         value=value, currency="INR", probability=100 if status == "won" else 0 if status == "lost" else st.probability, priority=prio, owner_id=users[owner].id, source=source,
                         status=status, created_at=created, closed_at=closed, stage_entered_at=closed or created + dt.timedelta(days=rnd.randint(1, 10)),
                         expected_close_date=(now + dt.timedelta(days=close_in)).date() if close_in is not None else None, position=rnd.randint(1, 9) * 1000.0,
                         lead_score=rnd.randint(40, 95), custom={"contract_length_months": rnd.choice([6, 12, 24])})
                db.session.add(d)
                db.session.flush()
                db.session.add(Activity(workspace_id=ws.id, type="created", title=f"Deal created in Lead", deal_id=d.id, company_id=d.company_id, contact_id=d.contact_id, user_id=d.owner_id, occurred_at=created, is_demo=True))
                if status == "open" and stage != "Lead":
                    db.session.add(Activity(workspace_id=ws.id, type="stage_changed", title=f"Moved from Qualified to {stage}", deal_id=d.id, company_id=d.company_id, contact_id=d.contact_id, user_id=d.owner_id,
                                            occurred_at=now - dt.timedelta(days=rnd.randint(0, 12)), is_demo=True, data={"to": stage}))
                if status in ("won", "lost"):
                    db.session.add(Activity(workspace_id=ws.id, type=status, title="Deal won 🎉" if status == "won" else "Deal lost", deal_id=d.id, company_id=d.company_id, contact_id=d.contact_id, user_id=d.owner_id,
                                            occurred_at=closed, is_demo=True))
                d.last_activity_at = closed or now - dt.timedelta(days=rnd.choice([0, 1, 2, 3, 5, 8, 12, 17]))
                return d

            open_deals = []
            for name, ci, contact_i, value, stage, owner, close_in, prio, source in DEALS:
                open_deals.append(make_deal(name, ci, contact_i, value, stage, owner, "open", now - dt.timedelta(days=rnd.randint(8, 60)), close_in=close_in, prio=prio, source=source))
            for name, ci, value, status, days_ago, owner in HISTORY:
                closed = now - dt.timedelta(days=days_ago)
                make_deal(name, ci, None, value, "Won" if status == "won" else "Lost", owner, status, closed - dt.timedelta(days=rnd.randint(14, 60)), closed=closed, source=rnd.choice(["referral", "website", "event"]))
            # a deal that has gone cold + one past its close date (they drive "needs attention")
            open_deals[6].last_activity_at = now - dt.timedelta(days=16)
            open_deals[12].last_activity_at = now - dt.timedelta(days=21)
            open_deals[4].expected_close_date = (now - dt.timedelta(days=4)).date()
            db.session.flush()

            def day(offset_days, hour):
                return (now + dt.timedelta(days=offset_days)).replace(hour=hour, minute=0, second=0, microsecond=0)

            task_rows = [
                ("Send revised proposal to Zenith", 0, 0, day(0, 15), "high", "todo", "follow_up", "deal", 0), ("Call Kabir about Saffron contract", 3, 11, day(0, 12), "urgent", "todo", "follow_up", "deal", 11),
                ("Prepare Vertex demo deck", 0, 8, day(1, 10), "medium", "in_progress", "task", "deal", 8), ("Follow up with Orbit CFO", 0, 3, day(-2, 16), "high", "todo", "follow_up", "deal", 3),
                ("Update Kavya pricing sheet", 1, 5, day(-1, 11), "medium", "todo", "task", "deal", 5), ("Intro call with Harborline", 0, 10, day(3, 14), "high", "todo", "follow_up", "deal", 10),
                ("Collect GreenLeaf requirements", 2, 4, day(4, 11), "low", "todo", "task", "deal", 4), ("Share case study with Nimbus", 0, 2, day(2, 17), "medium", "todo", "task", "deal", 2),
                ("Renewal check-in: Bluepeak", 1, 1, day(6, 10), "medium", "todo", "follow_up", "deal", 1), ("Sign NDA — Atlas", 3, 7, day(-5, 12), "low", "completed", "task", "deal", 7),
                ("Book onboarding call: Lumen", 0, 9, day(-3, 15), "medium", "completed", "task", "deal", 9), ("Quarterly pipeline review", 1, None, day(5, 11), "medium", "todo", "deadline", None, None),
                ("Clean up stale leads", 1, None, day(0, 18), "low", "todo", "task", None, None), ("Reply to Aarti Desai", 2, None, day(0, 10), "high", "todo", "follow_up", "lead", 0),
                ("Qualify Harsh Vora", 3, None, day(1, 12), "medium", "todo", "follow_up", "lead", 5), ("Send pricing to Isha Rastogi", 0, None, day(-1, 14), "high", "todo", "follow_up", "lead", 10),
            ]
            leads_q = db.session.query(Lead).filter_by(workspace_id=ws.id).order_by(Lead.created_at).all()
            for title, assignee, di, due, prio, status, kind, rel, idx in task_rows:
                t = Task(workspace_id=ws.id, title=title, assignee_id=users[assignee].id, created_by=users[0].id, due_at=due, priority=prio, status=status, kind=kind,
                         completed_at=due if status == "completed" else None)
                if rel == "deal":
                    t.deal_id, t.company_id, t.contact_id = open_deals[idx].id, open_deals[idx].company_id, open_deals[idx].contact_id
                elif rel == "lead":
                    t.lead_id = leads_q[idx].id
                db.session.add(t)
            for i, (title, h, d_off, ci) in enumerate([("Discovery call — Nimbus", min(now.hour + 2, 23), 0, 2), ("Proposal walkthrough — Vertex", 15, 0, 8), ("Contract review — Kavya", 12, 1, 5), ("Demo — Harborline APAC", 16, 2, 10),
                                                       ("QBR — Bluepeak", 10, -3, 1), ("Kickoff — Saffron", 14, -6, 11)]):
                past = d_off < 0
                m = Meeting(workspace_id=ws.id, title=title, starts_at=day(d_off, h), ends_at=day(d_off, h) + dt.timedelta(minutes=45), status="completed" if past else "scheduled", organizer_id=users[i % 3].id,
                            company_id=companies[ci].id, meeting_url="https://meet.example.com/" + title.split()[0].lower(), attendees=[{"name": "Prospect", "email": f"contact@{COMPANIES[ci][4]}"}],
                            summary="Walked through requirements. Agreed to send a revised proposal. Will schedule a follow up next week. Need to share security documentation." if past else None)
                db.session.add(m)
                db.session.add(Activity(workspace_id=ws.id, type="meeting", title=f"Meeting {'completed' if past else 'scheduled'}: {title}", company_id=companies[ci].id, user_id=m.organizer_id, occurred_at=m.starts_at, is_demo=True))
            for i, (outcome, ci) in enumerate([("connected", 0), ("no_answer", 3), ("interested", 5), ("follow_up_required", 8), ("not_interested", 12), ("connected", 11)]):
                when = now - dt.timedelta(days=rnd.randint(0, 9), hours=rnd.randint(1, 6))
                call = Call(workspace_id=ws.id, direction="outbound", status="completed", outcome=outcome, occurred_at=when, duration_seconds=rnd.randint(60, 900), user_id=users[i % 4].id, contact_id=contacts[[0, 3, 5, 8, 12, 11][i]].id,
                            company_id=companies[ci].id, notes="Discussed rollout timeline and budget.")
                db.session.add(call)
                db.session.add(Activity(workspace_id=ws.id, type="call", title=f"Call logged — {outcome.replace('_', ' ')}", contact_id=call.contact_id, company_id=companies[ci].id, user_id=call.user_id, occurred_at=when, is_demo=True))
            for i, (subject, ci) in enumerate([("Proposal: Fleet CRM rollout", 0), ("Re: Pricing questions", 2), ("Intro — CRM Wala x Orbit", 3), ("Next steps after demo", 8), ("Contract draft attached", 5), ("Quick question on integrations", 7)]):
                when = now - dt.timedelta(days=rnd.randint(0, 14), hours=rnd.randint(0, 8))
                c = contacts[[0, 2, 3, 8, 5, 7][i]]
                inbound = i in (1, 5)
                e = Email(workspace_id=ws.id, direction="inbound" if inbound else "outbound", status="received" if inbound else "sent", subject=subject, body="Hi,\n\nThanks for the update. Looping in the team — will revert shortly.\n\nRegards",
                          from_address=c.email if inbound else "aarav@acme.demo", to_addresses=["aarav@acme.demo"] if inbound else [c.email], user_id=users[0].id, sent_at=when, contact_id=c.id, company_id=c.company_id,
                          opens=0 if inbound else rnd.randint(0, 4), tracking_id=None if inbound else f"demo{i}{rnd.randint(1000, 9999)}")
                db.session.add(e)
                db.session.add(Activity(workspace_id=ws.id, type="email", title=f"Email {'received' if inbound else 'sent'}: {subject}", contact_id=c.id, company_id=c.company_id, user_id=users[0].id, occurred_at=when, is_demo=True))
            for i, body in enumerate(["Budget approved for Q4. Decision maker is the CFO — needs security review first.", "Prefers WhatsApp for quick updates. Timezone: IST evenings work best.",
                                       "Competitor in play: HubSpot. Differentiator is speed of setup and pricing in INR.", "Asked for a 12-month contract with quarterly billing.",
                                       "Champion is the Head of Ops. Wants a pilot with 10 users first."]):
                d = open_deals[[0, 3, 5, 8, 11][i]]
                db.session.add(Note(workspace_id=ws.id, body=body, author_id=users[i % 3].id, deal_id=d.id, company_id=d.company_id, contact_id=d.contact_id, pinned=i == 0, created_at=now - dt.timedelta(days=rnd.randint(0, 10))))
                db.session.add(Activity(workspace_id=ws.id, type="note", title="Note added", body=body, deal_id=d.id, company_id=d.company_id, contact_id=d.contact_id, user_id=users[i % 3].id, occurred_at=now - dt.timedelta(days=rnd.randint(0, 10)), is_demo=True))
            db.session.add(Automation(workspace_id=ws.id, name="Welcome & follow-up for new leads", description="Assign, tag, create a follow-up task, wait 2 days, then notify.", trigger_type="lead.created", is_active=True,
                                      created_by=users[0].id, run_count=18, last_run_at=now - dt.timedelta(hours=5), graph={
                "nodes": [{"id": "t", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {"trigger_type": "lead.created"}},
                          {"id": "a1", "type": "action", "position": {"x": 0, "y": 140}, "data": {"action_type": "assign_user", "config": {"strategy": "round_robin"}}},
                          {"id": "a2", "type": "action", "position": {"x": 0, "y": 280}, "data": {"action_type": "create_task", "config": {"title": "Call {{first_name}}", "due_in_days": 1, "priority": "high"}}},
                          {"id": "a3", "type": "action", "position": {"x": 0, "y": 420}, "data": {"action_type": "send_email", "config": {"to": "record", "subject": "Thanks for your interest, {{first_name}}", "body": "Hi {{first_name}},\n\nThanks for reaching out — we'll be in touch shortly.\n\nTeam Acme"}}},
                          {"id": "a4", "type": "action", "position": {"x": 0, "y": 560}, "data": {"action_type": "delay", "config": {"amount": 2, "unit": "days"}}},
                          {"id": "a5", "type": "action", "position": {"x": 0, "y": 700}, "data": {"action_type": "send_notification", "config": {"title": "Reminder: follow up with {{name}}", "body": "It's been 2 days.", "to": "owner"}}}],
                "edges": [{"id": "e1", "source": "t", "target": "a1"}, {"id": "e2", "source": "a1", "target": "a2"}, {"id": "e3", "source": "a2", "target": "a3"}, {"id": "e4", "source": "a3", "target": "a4"}, {"id": "e5", "source": "a4", "target": "a5"}]}))
            for title, body, ntype, link in [("New lead: Aarti Desai", "Referral · score 72", "new_lead", "/app/leads"), ("Kavya — Dealer network CRM moved to Negotiation", "Priya Sharma moved the deal", "deal_update", "/app/pipeline"),
                                             ("Task due today: Send revised proposal to Zenith", None, "task_assigned", "/app/tasks"), ("Your trial ends in 2 days", "Choose a plan to keep access", "trial_ending", "/app/billing")]:
                db.session.add(Notification(workspace_id=ws.id, user_id=users[0].id, type=ntype, title=title, body=body, link=link, created_at=now - dt.timedelta(hours=rnd.randint(1, 30))))
            ws.last_activity_at = now
            db.session.commit()
            counts = {"companies": len(companies), "contacts": len(contacts), "leads": len(LEADS), "deals": len(DEALS) + len(HISTORY), "tasks": len(task_rows)}
    return {"email": "demo@demo.crmwala.dev", "password": PASSWORD, "workspace": "Acme Demo Co", "counts": counts}
