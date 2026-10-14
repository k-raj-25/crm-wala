"""How-to articles the assistant can answer from ("How do I add a tower?"). Kept short; each points at the page to open."""
from __future__ import annotations

import re

ARTICLES: list[dict] = [
    {"title": "Add a project and draw its building", "url": "/app/projects?new=1", "keywords": "project building tower add new create",
     "body": "Projects → New project. Enter the name, city and stage, then add towers with the number of floors and flats per floor. Every flat appears on the building drawing."},
    {"title": "Add or edit a tower", "url": "/app/projects", "keywords": "tower block wing floors add edit",
     "body": "Open the project, then use Add tower (or the tower's menu → Edit). Floors and flats per floor generate the units automatically."},
    {"title": "Change a flat's status, hold it or mark it sold", "url": "/app/projects", "keywords": "flat unit status hold booked sold rent sale price",
     "body": "Open the project and click the flat on the building. In the drawer choose a status: For sale, For rent, On hold (pick hours and the lead), Booked, Sold or Rented."},
    {"title": "Add a lead (enquiry)", "url": "/app/leads", "keywords": "lead enquiry add create new customer buyer",
     "body": "Press C or the + button → Lead. Fill name, phone, what they want (buy/rent), size and budget. Or paste a WhatsApp message into the AI assistant and it fills the lead for you."},
    {"title": "Import leads from Excel or CSV", "url": "/app/settings/data", "keywords": "import excel csv spreadsheet upload bulk",
     "body": "Settings → Import & export. Upload the file, map the columns (or press Map with AI), review, then import. Duplicates are detected by phone and email."},
    {"title": "Convert a lead into a client", "url": "/app/leads", "keywords": "convert client contact customer deal",
     "body": "Open the lead and press Convert to client. You can also create a deal for the flat at the same time."},
    {"title": "Schedule a site visit", "url": "/app/calendar", "keywords": "site visit schedule meeting calendar appointment",
     "body": "Open the lead → Schedule meeting and pick Site visit, or use Calendar → Schedule event. You can link the project and flat."},
    {"title": "Set a follow-up reminder", "url": "/app/tasks", "keywords": "follow up reminder task callback daily plan",
     "body": "On a lead, set the Follow-up date in Details, or create a task. Daily Plan shows everything due today."},
    {"title": "Move a deal through the pipeline", "url": "/app/pipeline", "keywords": "deal pipeline stage kanban won lost",
     "body": "Pipeline shows deals by stage; drag a card to move it. Mark Won or Lost from the deal page."},
    {"title": "Invite your team", "url": "/app/settings/team", "keywords": "invite team user member staff agent add",
     "body": "Settings → Team → Invite. Choose a role; roles control what each person can see and change."},
    {"title": "Roles and permissions", "url": "/app/settings/roles", "keywords": "role permission access admin manager agent",
     "body": "Settings → Roles & permissions. Edit what each role can read, create, update and delete."},
    {"title": "Change lead statuses", "url": "/app/settings/lead-statuses", "keywords": "lead status stages custom",
     "body": "Settings → Lead statuses. Rename, recolour or add statuses."},
    {"title": "Custom fields", "url": "/app/settings/custom-fields", "keywords": "custom field extra column",
     "body": "Settings → Custom fields. Add fields to leads, clients, builders or deals."},
    {"title": "Email templates and sending email", "url": "/app/settings/email", "keywords": "email template gmail outlook mailbox send",
     "body": "Connect your mailbox in Settings → Email & templates, then use Email on any lead. Templates are under the same page."},
    {"title": "Build an automation", "url": "/app/automations", "keywords": "automation workflow auto assign round robin trigger",
     "body": "Automations → New automation, or type what you want in Describe it and the assistant builds it for you to review and switch on."},
    {"title": "Reports", "url": "/app/reports", "keywords": "report analytics revenue conversion source performance export",
     "body": "Reports has tiles for each question. You can also ask the assistant, e.g. 'Which source converted best last quarter?'."},
    {"title": "Receive 99acres leads", "url": "/app/integrations", "keywords": "99acres portal magicbricks housing integration leads",
     "body": "Integrations → 99acres gives you the forwarding address and push URL. New enquiries land as Awaiting review."},
    {"title": "Connect your AI key", "url": "/app/settings/ai", "keywords": "ai key openai chatgpt claude gemini api connect assistant settings",
     "body": "Settings → AI assistant. Pick your provider, paste the API key, press Test & save. Admins can switch features off and set monthly limits."},
    {"title": "Ask the assistant to make changes", "url": "/app/ai", "keywords": "ai do it for me update change approve assistant",
     "body": "Open the assistant (the ✨ button at the bottom right) and say what you want, e.g. 'Move Priya to Interested and remind me Friday'. Review the card and press Approve. You can undo for 30 seconds."},
    {"title": "Create a lead from a WhatsApp message, card photo or voice note", "url": "/app/leads", "keywords": "paste whatsapp photo visiting card voice capture",
     "body": "Leads → Capture with AI. Paste text, add a photo, or dictate; review the filled lead and press Approve."},
    {"title": "Log a site visit by voice", "url": "/app/leads", "keywords": "voice log visit after call dictate note",
     "body": "Open the lead → Log by voice. Speak what happened; the assistant prepares the visit, notes, budget change and follow-up for you to approve."},
    {"title": "My day briefing", "url": "/app/ai?tab=day", "keywords": "my day briefing morning plan today",
     "body": "AI Assistant → My day shows visits, follow-ups, cooling leads and expiring holds with one-tap actions."},
    {"title": "Search in plain words", "url": "/app/leads", "keywords": "search filter plain words natural ask ai view",
     "body": "On Leads press Ask AI next to search and type, e.g. '3BHK buyers in Sector 62 under 1.5 Cr not contacted in 10 days'. Save the result as a view."},
    {"title": "Billing and plan", "url": "/app/billing", "keywords": "billing plan upgrade payment invoice subscription",
     "body": "Billing & plan shows your plan, usage and invoices."},
    {"title": "Keyboard shortcuts", "url": "/app", "keywords": "shortcut keyboard hotkey",
     "body": "Press ? to see shortcuts. ⌘K searches, C creates, G then L opens Leads."},
]


def search(query: str, limit: int = 3) -> list[dict]:
    words = {w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 2}
    scored = []
    for a in ARTICLES:
        hay = set(re.findall(r"[a-z0-9]+", (a["title"] + " " + a["keywords"]).lower()))
        s = len(words & hay)
        if s:
            scored.append((s, a))
    scored.sort(key=lambda t: -t[0])
    return [a for _, a in scored[:limit]] or ARTICLES[:2]
