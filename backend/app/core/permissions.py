"""Permission catalog + default system roles. Roles/permissions are data (editable), this is the seed."""
from __future__ import annotations

CRUD = ("read", "create", "update", "delete")
RESOURCES = {
    "projects": "Projects",
    "units": "Inventory",
    "leads": "Leads",
    "contacts": "Contacts",
    "companies": "Companies",
    "deals": "Deals",
    "tasks": "Tasks",
    "notes": "Notes",
    "activities": "Activities",
    "meetings": "Meetings & calls",
    "emails": "Emails",
    "files": "Files",
    "pipelines": "Pipelines",
    "automations": "Automations",
}

PERMISSIONS: dict[str, tuple[str, str]] = {}
for _res, _label in RESOURCES.items():
    for _a in CRUD:
        PERMISSIONS[f"{_res}.{_a}"] = (_res, f"{_a.capitalize()} {_label.lower()}")
PERMISSIONS.update(
    {
        "leads.convert": ("leads", "Convert leads"),
        "deals.close": ("deals", "Mark deals won or lost"),
        "data.import": ("data", "Import data"),
        "data.export": ("data", "Export data"),
        "reports.read": ("reports", "View reports"),
        "reports.manage": ("reports", "Save and schedule reports"),
        "ai.use": ("ai", "Use the AI assistant"),
        "integrations.manage": ("integrations", "Manage integrations"),
        "team.read": ("team", "View team members"),
        "team.manage": ("team", "Invite and manage team members"),
        "roles.manage": ("team", "Manage roles and permissions"),
        "billing.manage": ("billing", "Manage billing and subscription"),
        "settings.manage": ("settings", "Manage workspace settings"),
        "audit.read": ("settings", "View audit log"),
    }
)

ALL = sorted(PERMISSIONS)


def _rw(*resources: str, delete: bool = True) -> list[str]:
    out = []
    for r in resources:
        out += [f"{r}.read", f"{r}.create", f"{r}.update"]
        if delete:
            out.append(f"{r}.delete")
    return out


_CORE = ["projects", "units", "leads", "contacts", "companies", "deals", "tasks", "notes", "activities", "meetings", "emails", "files"]

SYSTEM_ROLES: dict[str, dict] = {
    "owner": {
        "name": "Owner", "rank": 100, "description": "Full control, including billing and deleting the workspace.",
        "permissions": ["*"],
    },
    "admin": {
        "name": "Admin", "rank": 80, "description": "Manage everything except ownership and billing.",
        "permissions": [p for p in ALL if p != "billing.manage"],
    },
    "manager": {
        "name": "Manager", "rank": 60, "description": "Manage the team's pipeline, automations and reports.",
        "permissions": _rw(*_CORE, "pipelines", "automations")
        + ["leads.convert", "deals.close", "data.import", "data.export", "reports.read", "reports.manage", "ai.use",
           "team.read", "integrations.manage"],
    },
    "sales_rep": {
        "name": "Sales Representative", "rank": 40, "description": "Work leads, contacts, deals and tasks.",
        "permissions": _rw(*_CORE, delete=False) + ["pipelines.read", "automations.read", "leads.convert", "deals.close",
                                                    "data.export", "reports.read", "ai.use", "team.read"],
    },
    "viewer": {
        "name": "Viewer", "rank": 10, "description": "Read-only access.",
        "permissions": [f"{r}.read" for r in _CORE + ["pipelines", "automations"]] + ["reports.read", "team.read"],
    },
}


def has_permission(granted: list[str] | set[str], needed: str) -> bool:
    return "*" in granted or needed in granted
