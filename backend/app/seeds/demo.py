"""Realistic demo data for a real-estate brokerage. Everything lives in ONE workspace flagged is_demo=true with @demo.crmwala.dev
users, so it can never mix with production tenants and can be wiped with `flask seed-demo --reset`."""
from __future__ import annotations

import datetime as dt
import random

from app.core.passwords import hash_password
from app.core.tenant import bypass_scope, tenant_scope
from app.extensions import db
from app.models import (
    Activity, Automation, Call, Company, Contact, CustomFieldDef, Deal, Email, Lead, Meeting, Note, Notification, Pipeline, PipelineStage,
    Project, Tag, Task, Tower, Unit, UnitEvent, User, Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.services import inventory, scoring
from app.services.workspaces import create_workspace, seed_platform, system_role

PASSWORD = "Demo@12345"
SLUG = "sunrise-demo"
WORKSPACE = "Sunrise Realty"

BUILDERS = [  # name, website, city
    ("Ireo", "ireo.com", "Gurugram, IN"), ("Godrej Properties", "godrejproperties.com", "Mumbai, IN"), ("M3M India", "m3mindia.com", "Gurugram, IN"),
    ("DLF", "dlf.in", "Gurugram, IN"), ("Tata Housing", "tatahousing.com", "Mumbai, IN"), ("Sobha", "sobha.com", "Bengaluru, IN"),
]
# first, last, kind: owner | client
PEOPLE = [
    ("Rahul", "Khanna", "owner"), ("Ananya", "Iyer", "owner"), ("Karan", "Malhotra", "owner"), ("Ishita", "Banerjee", "owner"), ("Meera", "Nair", "owner"),
    ("Suresh", "Patel", "owner"), ("Zoya", "Fernandes", "owner"), ("Aditya", "Reddy", "owner"), ("Neha", "Gupta", "owner"), ("Pranav", "Joshi", "owner"),
    ("Wei", "Tan", "client"), ("Kabir", "Singh", "client"), ("Olivia", "Bennett", "client"), ("James", "Whitfield", "client"), ("Tara", "Shah", "client"),
    ("Arjun", "Menon", "client"), ("Riya", "Kulkarni", "client"), ("Dev", "Choudhary", "client"), ("Sana", "Qureshi", "client"), ("Nikhil", "Verma", "client"),
]
LEADS = [  # first, last, source, intent, bhk, budget_min, budget_max, location, status
    ("Aarti", "Desai", "99acres", "buy", "3 BHK", 2.0e7, 2.8e7, "Sector 67, Gurgaon", "new"), ("Mohit", "Agarwal", "magicbricks", "buy", "4 BHK", 3.0e7, 4.0e7, "Golf Course Ext. Road", "new"),
    ("Fatima", "Sheikh", "housing", "rent", "2 BHK", 4.0e4, 6.0e4, "Sector 67, Gurgaon", "contacted"), ("Gautam", "Bhatt", "referral", "buy", "3 BHK", 2.2e7, 2.6e7, "Sector 79, Gurgaon", "contacted"),
    ("Lakshmi", "Pillai", "walk_in", "buy", "3 BHK", 2.4e7, 3.0e7, "Sector 67, Gurgaon", "qualified"), ("Harsh", "Vora", "website", "invest", None, 5.0e7, 9.0e7, "Business Park", "new"),
    ("Simran", "Kaur", "instagram", "rent", "2 BHK", 3.0e4, 4.5e4, "Gurgaon", "unqualified"), ("Oliver", "Grant", "website", "rent", "3 BHK", 6.0e4, 9.0e4, "Golf Course Ext. Road", "qualified"),
    ("Pooja", "Hegde", "99acres", "buy", "2 BHK", 1.4e7, 1.8e7, "Sector 67, Gurgaon", "contacted"), ("Yash", "Thakur", "facebook_ads", "buy", "3 BHK", 2.0e7, 2.5e7, "Sector 79, Gurgaon", "new"),
    ("Isha", "Rastogi", "magicbricks", "rent", "3 BHK", 5.5e4, 7.0e4, "Sector 67, Gurgaon", "new"), ("Rohan", "Bose", "referral", "buy", "4 BHK", 3.2e7, 4.5e7, "Golf Course Ext. Road", "qualified"),
    ("Tanvi", "Mishra", "housing", "buy", "2 BHK", 1.2e7, 1.6e7, "Gurgaon", "contacted"), ("Farhan", "Ali", "referral", "invest", None, 2.0e7, 4.0e7, "Business Park", "contacted"),
    ("Naina", "Saxena", "instagram", "buy", "3 BHK", 2.5e7, 3.0e7, "Sector 67, Gurgaon", "new"), ("Siddharth", "Rao", "website", "buy", "3 BHK", 2.3e7, 2.8e7, "Sector 79, Gurgaon", "qualified"),
    ("Kritika", "Jain", "99acres", "rent", "2 BHK", 3.5e4, 5.0e4, "Gurgaon", "lost"), ("Victor", "D'Souza", "walk_in", "buy", "4 BHK", 3.5e7, 5.0e7, "Golf Course Ext. Road", "new"),
    ("Anjali", "Mukherjee", "facebook_ads", "buy", "2 BHK", 1.3e7, 1.7e7, "Sector 67, Gurgaon", "contacted"), ("Bharat", "Solanki", "referral", "invest", None, 8.0e7, 1.5e8, "Business Park", "new"),
    ("Divya", "Krishnan", "housing", "rent", "3 BHK", 5.0e4, 7.5e4, "Sector 79, Gurgaon", "new"), ("Eshan", "Kapoor", "website", "buy", "3 BHK", 2.2e7, 2.7e7, "Sector 67, Gurgaon", "contacted"),
    ("Gita", "Venkat", "magicbricks", "buy", "4 BHK", 3.0e7, 3.8e7, "Golf Course Ext. Road", "new"), ("Hrithik", "Sen", "instagram", "rent", "2 BHK", 3.5e4, 5.5e4, "Gurgaon", "contacted"),
    ("Jasmine", "Dhillon", "referral", "buy", "3 BHK", 2.4e7, 2.9e7, "Sector 67, Gurgaon", "qualified"), ("Kunal", "Tripathi", "99acres", "buy", "2 BHK", 1.5e7, 1.9e7, "Sector 79, Gurgaon", "unqualified"),
    ("Leena", "George", "walk_in", "rent", "3 BHK", 6.0e4, 8.0e4, "Sector 67, Gurgaon", "new"), ("Manish", "Pandey", "housing", "buy", "3 BHK", 2.1e7, 2.6e7, "Sector 79, Gurgaon", "contacted"),
    ("Nandini", "Roy", "website", "buy", "4 BHK", 3.3e7, 4.2e7, "Golf Course Ext. Road", "new"), ("Omkar", "Patil", "99acres", "invest", None, 3.0e7, 6.0e7, "Business Park", "new"),
]
# D-13 as drawn in the product brief (floor 10 → ground, four flats a floor). v=vacant s=for sale r=rented o=self occupied
# h=on hold b=booked d=sold l=for rent
D13 = {10: "vrvs", 9: "ovrv", 8: "vsvr", 7: "vvov", 6: "rvhv", 5: "vrvo", 4: "bsrv", 3: "vdvo", 2: "rvlr", 1: "vorv", 0: "osdr"}
CODE = {"v": "vacant", "s": "for_sale", "r": "rented", "o": "self_occupied", "h": "on_hold", "b": "booked", "d": "sold", "l": "for_rent"}
LAYOUT = [("3 BHK", 1850, "North"), ("2 BHK", 1250, "East"), ("3 BHK", 1750, "South"), ("4 BHK", 2450, "West")]
STATUS_WEIGHTS = [("vacant", 34), ("for_sale", 16), ("for_rent", 8), ("on_hold", 4), ("booked", 6), ("sold", 14), ("rented", 12), ("self_occupied", 6)]

# (name, builder idx, sector, locality, kind, stage, [(tower, floors, per_floor, has_ground, unit_kind, base price/sqft, layout)])
PROJECTS = [
    ("Ireo Victory Valley", 0, "Sector 67", "Golf Course Ext. Road", "residential", "ready",
     [("Tower D-13", 10, 4, True, "apartment", 13500, LAYOUT), ("Tower D-12", 12, 4, True, "apartment", 13200, LAYOUT)]),
    ("Godrej Aria", 1, "Sector 79", "New Gurgaon", "residential", "under_construction", [("Tower A", 9, 6, False, "apartment", 11800, LAYOUT + LAYOUT[:2])]),
    ("M3M Urbana Business Park", 2, "Sector 67A", "Golf Course Ext. Road", "commercial", "ready", [("Block 1", 5, 6, True, "office", 16500, [("Office", 900, "North"), ("Office", 1400, "East")] * 3)]),
]
STAGE_PLAN = [("Enquiry", 3), ("Site Visit", 3), ("Shortlisted", 2), ("Negotiation", 2), ("Token Paid", 1)]


def _wipe() -> None:
    with bypass_scope():
        for ws in db.session.query(Workspace).filter(Workspace.slug.in_((SLUG, "acme-demo"))).all():  # "acme-demo" = the pre-real-estate demo
            db.session.delete(ws)
        db.session.flush()
        db.session.query(User).filter(User.email.like("%@demo.crmwala.dev")).delete(synchronize_session=False)
        db.session.commit()


def _pick_status(rnd: random.Random) -> str:
    return rnd.choices([s for s, _ in STATUS_WEIGHTS], weights=[w for _, w in STATUS_WEIGHTS])[0]


def seed_demo(reset: bool = False, plan: str = "trial") -> dict:
    rnd = random.Random(42)
    now = utcnow()
    with bypass_scope():
        seed_platform()
    if reset:
        _wipe()
    with bypass_scope():
        if db.session.query(Workspace).filter_by(slug=SLUG).first():
            return {"email": "demo@demo.crmwala.dev", "password": PASSWORD, "workspace": f"{WORKSPACE} (already exists — use --reset to recreate)", "counts": "unchanged"}
        pw = hash_password(PASSWORD)
        team = [("Aarav Mehta", "demo@demo.crmwala.dev", "owner"), ("Priya Sharma", "priya@demo.crmwala.dev", "manager"), ("Rohit Verma", "rohit@demo.crmwala.dev", "sales_rep"),
                ("Sneha Kapoor", "sneha@demo.crmwala.dev", "sales_rep"), ("Vikram Rao", "vikram@demo.crmwala.dev", "viewer")]
        users: list[User] = []
        for name, email, _ in team:
            u = User(name=name, email=email, password_hash=pw, email_verified_at=now, last_login_at=now - dt.timedelta(hours=rnd.randint(1, 48)))
            db.session.add(u)
            users.append(u)
        db.session.flush()
        ws = create_workspace(users[0], WORKSPACE, company_size="11-50", industry="Real estate", is_demo=True)
        ws.slug, ws.sales_model, ws.goals = SLUG, "b2c", ["manage_leads", "track_deals", "analyze_revenue"]
        ws.onboarding_completed_at = now
        ws.trial_ends_at, ws.trial_started_at = now + dt.timedelta(days=2, hours=3), now - dt.timedelta(hours=21)
        if plan != "trial":
            ws.plan_key, ws.subscription_status, ws.billing_interval = plan, "active", "monthly"
            ws.current_period_end = now + dt.timedelta(days=21)
        for u, (_, _, role) in list(zip(users, team))[1:]:
            db.session.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role_id=system_role(role).id))
        db.session.flush()
        with tenant_scope(ws.id):
            pipeline = db.session.query(Pipeline).filter_by(workspace_id=ws.id).one()
            stages = {s.name: s for s in db.session.query(PipelineStage).filter_by(pipeline_id=pipeline.id)}
            for t, c in (("hot", "#ef4444"), ("nri", "#6366f1"), ("investor", "#f59e0b"), ("first-time-buyer", "#10b981"), ("ready-to-move", "#0ea5e9")):
                db.session.add(Tag(workspace_id=ws.id, name=t, color=c))
            db.session.add(CustomFieldDef(workspace_id=ws.id, entity_type="contact", key="preferred_language", label="Preferred language", field_type="dropdown", options=["English", "Hindi", "Punjabi"], position=0))
            db.session.add(CustomFieldDef(workspace_id=ws.id, entity_type="deal", key="payment_plan", label="Payment plan", field_type="dropdown", options=["Down payment", "Construction linked", "Possession linked"], position=0))

            builders = []
            for name, site, loc in BUILDERS:
                c = Company(workspace_id=ws.id, name=name, industry="Real estate developer", location=loc, website=f"https://{site}", domain=site, owner_id=users[0].id,
                            created_at=now - dt.timedelta(days=rnd.randint(60, 300)))
                db.session.add(c)
                builders.append(c)
            db.session.flush()
            contacts: list[Contact] = []
            for first, last, kind in PEOPLE:
                c = Contact(workspace_id=ws.id, first_name=first, last_name=last, email=f"{first.lower()}.{last.lower()}@gmail.com", phone=f"+91 9{rnd.randint(100000000, 999999999)}",
                            job_title="Flat owner" if kind == "owner" else "Client", owner_id=users[rnd.randint(0, 3)].id, location="Gurgaon",
                            created_at=now - dt.timedelta(days=rnd.randint(5, 150)), custom={"preferred_language": rnd.choice(["English", "Hindi"])},
                            tags=["nri"] if rnd.random() < 0.12 else [], last_contacted_at=now - dt.timedelta(days=rnd.randint(0, 30)))
                db.session.add(c)
                contacts.append(c)
            db.session.flush()
            owners, clients = contacts[:10], contacts[10:]

            # ---- projects, towers, units ---------------------------------------------------------------------------
            all_units: list[Unit] = []
            projects: list[Project] = []
            for pname, bi, sector, locality, pkind, pstage, towers in PROJECTS:
                p = Project(workspace_id=ws.id, name=pname, developer=BUILDERS[bi][0], kind=pkind, stage=pstage, city="Gurgaon", locality=locality, sector=sector,
                            rera_id=f"RC/REP/HARERA/GGM/{rnd.randint(100, 999)}/{rnd.randint(10, 99)}/2023", owner_id=users[0].id,
                            amenities=["Clubhouse", "Swimming pool", "Gym", "Kids play area", "24x7 security", "Power backup"],
                            possession_date=(now + dt.timedelta(days=500)).date() if pstage != "ready" else None,
                            description=f"{pname} by {BUILDERS[bi][0]} in {sector}, Gurgaon.", created_at=now - dt.timedelta(days=rnd.randint(100, 400)))
                db.session.add(p)
                db.session.flush()
                projects.append(p)
                for ti, (tname, floors, per, ground, ukind, psf, layout) in enumerate(towers):
                    t = Tower(workspace_id=ws.id, project_id=p.id, name=tname, floors=floors, has_ground=ground, position=ti, status="active")
                    db.session.add(t)
                    db.session.flush()
                    for f in ([0] if ground else []) + list(range(1, floors + 1)):
                        for pos in range(1, per + 1):
                            bhk, area, facing = layout[(pos - 1) % len(layout)]
                            code = D13.get(f, "")[pos - 1] if tname == "Tower D-13" and pname == "Ireo Victory Valley" else None
                            status = CODE[code] if code else _pick_status(rnd)
                            price = round(area * (psf + f * 45) / 1e5) * 1e5  # a little more for higher floors
                            rent = round(area * (psf / 250) / 500) * 500
                            u = Unit(workspace_id=ws.id, project_id=p.id, tower_id=t.id, floor=f, position=pos, number=inventory.unit_number(f, pos), kind=ukind,
                                     bhk=bhk if ukind == "apartment" else None, area_sqft=area, facing=facing, status=status,
                                     sale_price=price if status in ("vacant", "for_sale", "on_hold", "booked", "sold") else None,
                                     monthly_rent=rent if status in ("for_rent", "rented") or (status == "vacant" and rnd.random() < 0.3) else None,
                                     status_changed_at=now - dt.timedelta(days=rnd.randint(1, 150), hours=rnd.randint(0, 20)),
                                     owner_contact_id=rnd.choice(owners).id if status != "vacant" or rnd.random() < 0.4 else None)
                            if status in ("sold", "rented", "booked"):
                                u.occupant_contact_id = rnd.choice(clients).id
                            if status == "on_hold":
                                u.hold_until = now + dt.timedelta(hours=rnd.choice([6, 20, 30, 70]))
                                u.held_by = users[rnd.randint(1, 3)].id
                            db.session.add(u)
                            all_units.append(u)
            db.session.flush()
            for u in all_units:
                if u.status != "vacant":
                    db.session.add(UnitEvent(workspace_id=ws.id, unit_id=u.id, type="status", from_status="vacant", to_status=u.status, user_id=users[rnd.randint(0, 3)].id,
                                             created_at=u.status_changed_at, note="Hold placed for a client" if u.status == "on_hold" else None))
            db.session.flush()

            # ---- leads -----------------------------------------------------------------------------------------------
            available = [u for u in all_units if u.status in ("for_sale", "vacant") and u.sale_price]
            leads: list[Lead] = []
            for i, (first, last, source, intent, bhk, lo, hi, loc, status) in enumerate(LEADS):
                contacted = None if status == "new" else now - dt.timedelta(days=rnd.choice([1, 2, 3, 5, 9, 12, 20]))
                interest = rnd.choice(available) if i % 3 == 0 else None
                lead = Lead(workspace_id=ws.id, first_name=first, last_name=last, email=f"{first.lower()}.{last.lower().replace(chr(39), '')}@gmail.com",
                            phone=f"+91 8{rnd.randint(100000000, 999999999)}", source=source, status=status, owner_id=users[i % 4].id, intent=intent,
                            property_type="office" if intent == "invest" else "apartment", bhk=bhk, budget_min=lo, budget_max=hi, location=loc,
                            project_id=interest.project_id if interest else None, unit_id=interest.id if interest else None,
                            created_at=now - dt.timedelta(days=rnd.randint(0, 45), hours=rnd.randint(0, 20)), last_contacted_at=contacted,
                            tags=(["hot"] if i % 7 == 0 else []) + (["investor"] if intent == "invest" else []) + (["first-time-buyer"] if i % 9 == 4 else []))
                if status in ("new", "contacted", "qualified"):
                    offset = rnd.choice([-3, -1, 0, 0, 1, 2, 5, None])
                    lead.next_follow_up_at = (now.replace(hour=11, minute=0) + dt.timedelta(days=offset)) if offset is not None else None
                lead.score, lead.score_reasons = scoring.score_lead(lead, rnd.randint(0, 3))
                db.session.add(lead)
                db.session.flush()
                leads.append(lead)
                db.session.add(Activity(workspace_id=ws.id, type="created", title="Enquiry received", lead_id=lead.id, user_id=lead.owner_id, occurred_at=lead.created_at, is_demo=True))
                if contacted:
                    db.session.add(Activity(workspace_id=ws.id, type="call", title="Call logged — connected", lead_id=lead.id, user_id=lead.owner_id, occurred_at=contacted, is_demo=True))
                    lead.last_activity_at = contacted
            db.session.flush()

            # ---- deals (property bookings) ---------------------------------------------------------------------------
            def make_deal(name, unit, contact, stage, owner, status, created, closed=None, close_in=None, prio="medium", source="referral", value=None):
                st = stages[stage]
                price = value if value is not None else float(unit.sale_price or unit.monthly_rent or 0)
                d = Deal(workspace_id=ws.id, name=name, contact_id=contact.id if contact else None, pipeline_id=pipeline.id, stage_id=st.id, value=price, currency="INR",
                         probability=100 if status == "won" else 0 if status == "lost" else st.probability, priority=prio, owner_id=users[owner].id, source=source, status=status,
                         created_at=created, closed_at=closed, stage_entered_at=closed or created + dt.timedelta(days=rnd.randint(1, 8)),
                         expected_close_date=(now + dt.timedelta(days=close_in)).date() if close_in is not None else None, position=rnd.randint(1, 9) * 1000.0,
                         lead_score=rnd.randint(40, 95), unit_id=unit.id if unit else None, project_id=unit.project_id if unit else None,
                         custom={"payment_plan": rnd.choice(["Down payment", "Construction linked", "Possession linked"])})
                db.session.add(d)
                db.session.flush()
                db.session.add(Activity(workspace_id=ws.id, type="created", title="Deal created in Enquiry", deal_id=d.id, contact_id=d.contact_id, user_id=d.owner_id, occurred_at=created, is_demo=True))
                if status == "open" and stage != "Enquiry":
                    db.session.add(Activity(workspace_id=ws.id, type="stage_changed", title=f"Moved to {stage}", deal_id=d.id, contact_id=d.contact_id, user_id=d.owner_id,
                                            occurred_at=now - dt.timedelta(days=rnd.randint(0, 12)), is_demo=True, data={"to": stage}))
                if status in ("won", "lost"):
                    db.session.add(Activity(workspace_id=ws.id, type=status, title="Deal closed 🎉" if status == "won" else "Deal lost", deal_id=d.id, contact_id=d.contact_id, user_id=d.owner_id, occurred_at=closed, is_demo=True))
                d.last_activity_at = closed or now - dt.timedelta(days=rnd.choice([0, 1, 2, 3, 5, 8, 12, 17]))
                return d

            open_deals: list[Deal] = []
            targets = [u for u in all_units if u.status in ("booked", "on_hold", "for_sale")]
            rnd.shuffle(targets)
            slot = 0
            for stage, n in STAGE_PLAN:
                for _ in range(n):
                    u = targets[slot]
                    cl = rnd.choice(clients)
                    open_deals.append(make_deal(f"{cl.name} — {u.name}, {next(p.name for p in projects if p.id == u.project_id)}", u, cl, stage, 1 + slot % 3, "open",
                                                now - dt.timedelta(days=rnd.randint(6, 50)), close_in=rnd.randint(3, 60), prio=rnd.choice(["medium", "high", "urgent"])))
                    slot += 1
            for u in [x for x in all_units if x.status == "sold"][:14]:
                closed = u.status_changed_at
                make_deal(f"{rnd.choice(clients).name} — {u.name}", u, u.occupant_contact_id and next(c for c in clients if c.id == u.occupant_contact_id), "Closed", rnd.randint(0, 3), "won",
                          closed - dt.timedelta(days=rnd.randint(14, 45)), closed=closed, source=rnd.choice(["referral", "99acres", "walk_in"]))
            for i in range(5):
                closed = now - dt.timedelta(days=rnd.randint(5, 120))
                make_deal(f"{rnd.choice(clients).name} — rental", None, rnd.choice(clients), "Closed" if i < 2 else "Lost", rnd.randint(0, 3), "won" if i < 2 else "lost",
                          closed - dt.timedelta(days=rnd.randint(7, 30)), closed=closed, value=rnd.choice([55000, 62000, 48000, 75000, 41000]), source="housing")
            open_deals[4].last_activity_at = now - dt.timedelta(days=16)
            open_deals[7].expected_close_date = (now - dt.timedelta(days=4)).date()
            db.session.flush()

            def day(offset_days, hour):
                return (now + dt.timedelta(days=offset_days)).replace(hour=hour, minute=0, second=0, microsecond=0)

            # ---- site visits, tasks, calls, emails, notes -----------------------------------------------------------
            visit_units = rnd.sample([u for u in all_units if u.status in ("for_sale", "vacant", "for_rent")], 8)
            for i, (d_off, hour) in enumerate([(0, min(now.hour + 2, 20)), (0, 17), (1, 11), (1, 16), (2, 10), (3, 12), (-2, 11), (-4, 15)]):
                u, ld = visit_units[i], leads[i * 3 % len(leads)]
                past = d_off < 0
                pname = next(p.name for p in projects if p.id == u.project_id)
                m = Meeting(workspace_id=ws.id, title=f"Site visit — {ld.name}, {u.name}", kind="site_visit", starts_at=day(d_off, hour), ends_at=day(d_off, hour) + dt.timedelta(minutes=45),
                            status="completed" if past else "scheduled", organizer_id=users[i % 3].id, lead_id=ld.id, unit_id=u.id, project_id=u.project_id, location=f"{pname}, Gurgaon",
                            summary="Liked the layout and the view. Wants to discuss the payment plan with family." if past else None)
                db.session.add(m)
                db.session.add(Activity(workspace_id=ws.id, type="meeting", title=f"Site visit {'completed' if past else 'scheduled'}: {u.name}", lead_id=ld.id, user_id=m.organizer_id, occurred_at=m.starts_at, is_demo=True))
            task_rows = [
                ("Call back {0} about the floor plan", 0, 0, 0, "high", "todo", "follow_up"), ("Send brochure and price sheet to {0}", 0, 2, 0, "medium", "todo", "follow_up"),
                ("Confirm site visit with {0}", 3, 4, 0, "urgent", "todo", "follow_up"), ("Collect token cheque from {0}", 0, 6, 1, "high", "todo", "follow_up"),
                ("Share loan eligibility checklist with {0}", 1, 8, -1, "medium", "todo", "task"), ("Negotiation call with {0}", 0, 10, -2, "high", "todo", "follow_up"),
                ("Send agreement draft to {0}", 2, 12, 2, "medium", "todo", "task"), ("Follow up on hold expiry for {0}", 3, 14, 0, "high", "todo", "follow_up"),
                ("Update floor prices for Tower D-12", 1, None, 5, "medium", "todo", "deadline"), ("Collect owner feedback for 2 BHK listings", 1, None, 0, "low", "todo", "task"),
                ("Re-list vacant flats on 99acres", 0, None, -3, "low", "completed", "task"),
            ]
            for title, assignee, li, off, prio, status, kind in task_rows:
                t = Task(workspace_id=ws.id, title=title.format(leads[li].first_name if li is not None else ""), assignee_id=users[assignee].id, created_by=users[0].id, due_at=day(off, 12 + (assignee % 4)),
                         priority=prio, status=status, kind=kind, completed_at=day(off, 12) if status == "completed" else None, lead_id=leads[li].id if li is not None else None)
                db.session.add(t)
            for i, outcome in enumerate(["connected", "no_answer", "interested", "follow_up_required", "not_interested", "connected"]):
                when = now - dt.timedelta(days=rnd.randint(0, 9), hours=rnd.randint(1, 6))
                call = Call(workspace_id=ws.id, direction="outbound", status="completed", outcome=outcome, occurred_at=when, duration_seconds=rnd.randint(60, 900), user_id=users[i % 4].id,
                            lead_id=leads[i + 2].id, notes="Discussed budget, preferred floor and possession timeline.")
                db.session.add(call)
                db.session.add(Activity(workspace_id=ws.id, type="call", title=f"Call logged — {outcome.replace('_', ' ')}", lead_id=call.lead_id, user_id=call.user_id, occurred_at=when, is_demo=True))
            for i, subject in enumerate(["Brochure & price sheet — Ireo Victory Valley", "Re: Is the 3 BHK on the 8th floor still available?", "Site visit confirmation for Saturday", "Payment plan options"]):
                when = now - dt.timedelta(days=rnd.randint(0, 14), hours=rnd.randint(0, 8))
                c = clients[i]
                inbound = i == 1
                db.session.add(Email(workspace_id=ws.id, direction="inbound" if inbound else "outbound", status="received" if inbound else "sent", subject=subject,
                                     body="Hi,\n\nThanks for the details. We would like to visit this weekend.\n\nRegards", from_address=c.email if inbound else "aarav@sunrise.demo",
                                     to_addresses=["aarav@sunrise.demo"] if inbound else [c.email], user_id=users[0].id, sent_at=when, contact_id=c.id,
                                     opens=0 if inbound else rnd.randint(0, 4), tracking_id=None if inbound else f"demo{i}{rnd.randint(1000, 9999)}"))
                db.session.add(Activity(workspace_id=ws.id, type="email", title=f"Email {'received' if inbound else 'sent'}: {subject}", contact_id=c.id, user_id=users[0].id, occurred_at=when, is_demo=True))
            for i, body in enumerate(["Wants a vastu-compliant east-facing flat above the 6th floor.", "Pre-approved home loan up to ₹2.5 Cr. Decision in two weeks.",
                                      "NRI client — prefers WhatsApp. Family visits in December.", "Comparing with Godrej Aria. Our edge: ready to move in."]):
                ld = leads[[0, 4, 11, 15][i]]
                db.session.add(Note(workspace_id=ws.id, body=body, author_id=users[i % 3].id, lead_id=ld.id, pinned=i == 0, created_at=now - dt.timedelta(days=rnd.randint(0, 10))))
            db.session.add(Automation(workspace_id=ws.id, name="New enquiry: assign, call task, send brochure", description="Assign the enquiry, create a call task, email the brochure, wait 2 days and remind.",
                                      trigger_type="lead.created", is_active=True, created_by=users[0].id, run_count=18, last_run_at=now - dt.timedelta(hours=5), graph={
                "nodes": [{"id": "t", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {"trigger_type": "lead.created"}},
                          {"id": "a1", "type": "action", "position": {"x": 0, "y": 140}, "data": {"action_type": "assign_user", "config": {"strategy": "round_robin"}}},
                          {"id": "a2", "type": "action", "position": {"x": 0, "y": 280}, "data": {"action_type": "create_task", "config": {"title": "Call {{first_name}} within the hour", "due_in_days": 1, "priority": "high"}}},
                          {"id": "a3", "type": "action", "position": {"x": 0, "y": 420}, "data": {"action_type": "send_email", "config": {"to": "record", "subject": "Thanks for your enquiry, {{first_name}}", "body": "Hi {{first_name}},\n\nThank you for your interest. I'll call you shortly to understand what you're looking for and arrange a visit.\n\nSunrise Realty"}}},
                          {"id": "a4", "type": "action", "position": {"x": 0, "y": 560}, "data": {"action_type": "delay", "config": {"amount": 2, "unit": "days"}}},
                          {"id": "a5", "type": "action", "position": {"x": 0, "y": 700}, "data": {"action_type": "send_notification", "config": {"title": "Follow up with {{name}}", "body": "It's been 2 days since the enquiry.", "to": "owner"}}}],
                "edges": [{"id": "e1", "source": "t", "target": "a1"}, {"id": "e2", "source": "a1", "target": "a2"}, {"id": "e3", "source": "a2", "target": "a3"}, {"id": "e4", "source": "a3", "target": "a4"}, {"id": "e5", "source": "a4", "target": "a5"}]}))
            for title, body, ntype, link in [("New enquiry: Aarti Desai", "99acres · 3 BHK · ₹2–2.8 Cr", "new_lead", "/app/leads"), ("A hold expires today", "Unit 604, Tower D-13", "deal_update", "/app/projects"),
                                             ("Site visit today: Gautam Bhatt", None, "task_assigned", "/app/calendar"), ("Your trial ends in 2 days", "Choose a plan to keep access", "trial_ending", "/app/billing")]:
                db.session.add(Notification(workspace_id=ws.id, user_id=users[0].id, type=ntype, title=title, body=body, link=link, created_at=now - dt.timedelta(hours=rnd.randint(1, 30))))
            ws.last_activity_at = now
            db.session.commit()
            counts = {"projects": len(projects), "units": len(all_units), "leads": len(leads), "contacts": len(contacts), "deals": db.session.query(Deal).count()}
    return {"email": "demo@demo.crmwala.dev", "password": PASSWORD, "workspace": WORKSPACE, "counts": counts}
