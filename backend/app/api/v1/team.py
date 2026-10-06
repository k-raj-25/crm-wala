from __future__ import annotations

import datetime as dt
import uuid

from flask import Blueprint, current_app, g, request
from pydantic import Field
from sqlalchemy import func, or_

from app.core import crypto
from app.core.auth import protect, require
from app.core.crud import MAX_PER_PAGE, parse_date
from app.core.errors import ApiError, conflict, forbidden, not_found
from app.core.permissions import ALL, PERMISSIONS
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import AuditLog, Invitation, Permission, Role, Team, User, WorkspaceMember
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse, provided
from app.services import analytics, audit
from app.services import email as email_service
from app.services.usage import check_limit

bp = Blueprint("team", __name__, url_prefix="/api/v1")


def _my_rank() -> int:
    return g.member.role.rank


def _member_dict(m: WorkspaceMember) -> dict:
    u = m.user
    return {"id": str(m.id), "user_id": str(u.id), "name": u.name, "email": u.email, "avatar_url": u.avatar_url, "status": m.status,
            "role": {"id": str(m.role.id), "key": m.role.key, "name": m.role.name, "rank": m.role.rank}, "team_id": str(m.team_id) if m.team_id else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None, "joined_at": m.created_at.isoformat(),
            "mfa_enabled": u.totp_enabled}


def _available_roles() -> list[Role]:
    return db.session.query(Role).filter(or_(Role.workspace_id.is_(None), Role.workspace_id == g.workspace.id)).order_by(Role.rank.desc()).all()


def _role_or_404(role_id) -> Role:
    r = db.session.query(Role).filter(Role.id == role_id, or_(Role.workspace_id.is_(None), Role.workspace_id == g.workspace.id)).one_or_none()
    if r is None:
        raise not_found("Role")
    return r


@bp.get("/team/members")
@protect("team.read")
def list_members():
    rows = db.session.query(WorkspaceMember).filter_by(workspace_id=g.workspace.id).join(User).order_by(User.name).all()
    return ok([_member_dict(m) for m in rows])


class MemberPatch(Schema):
    role_id: uuid.UUID | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    team_id: uuid.UUID | None = None


@bp.patch("/team/members/<uuid:mid>")
@protect("team.manage")
def update_member(mid):
    m = db.session.query(WorkspaceMember).filter_by(id=mid, workspace_id=g.workspace.id).one_or_none()
    if m is None:
        raise not_found("Member")
    ch = provided(parse(MemberPatch))
    if m.role.key == "owner":
        raise forbidden("The owner's role can't be changed", "owner_protected")
    if m.role.rank >= _my_rank() and g.member.role.key != "owner":
        raise forbidden("You can't manage someone with an equal or higher role", "rank_too_low")
    before = {"role": m.role.key, "status": m.status}
    if ch.get("role_id"):
        role = _role_or_404(ch["role_id"])
        if role.key == "owner":
            raise forbidden("Ownership can't be assigned here", "owner_protected")
        if role.rank > _my_rank():
            raise forbidden("You can't grant a role higher than your own", "rank_too_low")
        m.role_id = role.id
    if "status" in ch and ch["status"]:
        m.status = ch["status"]
        if ch["status"] == "disabled":
            from app.models import UserSession

            db.session.query(UserSession).filter_by(user_id=m.user_id, workspace_id=g.workspace.id, revoked_at=None).update({"revoked_at": utcnow()})
    if "team_id" in ch:
        if ch["team_id"] and not db.session.query(Team).filter_by(id=ch["team_id"], workspace_id=g.workspace.id).first():
            raise ApiError(422, "validation_error", "Team not found", {"team_id": "Not found"})
        m.team_id = ch["team_id"]
    db.session.flush()
    db.session.refresh(m)
    audit.record("team.member_updated", entity_type="user", entity_id=m.user_id, summary=f"Updated {m.user.email}", before=before,
                 after={"role": m.role.key, "status": m.status})
    db.session.commit()
    return ok(_member_dict(m))


@bp.delete("/team/members/<uuid:mid>")
@protect("team.manage")
def remove_member(mid):
    m = db.session.query(WorkspaceMember).filter_by(id=mid, workspace_id=g.workspace.id).one_or_none()
    if m is None:
        raise not_found("Member")
    if m.role.key == "owner":
        raise forbidden("The owner can't be removed", "owner_protected")
    if m.role.rank >= _my_rank() and g.member.role.key != "owner":
        raise forbidden("You can't remove someone with an equal or higher role", "rank_too_low")
    from app.models import Contact, Company, Deal, Lead, Task, UserSession

    # Hand their records back to the person removing them so nothing is orphaned.
    for model, col in ((Lead, "owner_id"), (Contact, "owner_id"), (Company, "owner_id"), (Deal, "owner_id"), (Task, "assignee_id")):
        db.session.query(model).filter(model.workspace_id == g.workspace.id, getattr(model, col) == m.user_id).update({col: g.user.id})
    db.session.query(UserSession).filter_by(user_id=m.user_id, workspace_id=g.workspace.id, revoked_at=None).update({"revoked_at": utcnow()})
    audit.record("team.member_removed", entity_type="user", entity_id=m.user_id, summary=f"Removed {m.user.email} from the workspace")
    db.session.delete(m)
    db.session.commit()
    return no_content()


# ---- invitations ------------------------------------------------------------------------

class InviteIn(Schema):
    email: Email
    role_id: uuid.UUID


def _inv_dict(i: Invitation) -> dict:
    return {"id": str(i.id), "email": i.email, "role": {"id": str(i.role.id), "name": i.role.name, "key": i.role.key},
            "expires_at": i.expires_at.isoformat(), "created_at": i.created_at.isoformat()}


@bp.get("/team/invitations")
@protect("team.manage")
def list_invitations():
    rows = db.session.query(Invitation).filter(Invitation.workspace_id == g.workspace.id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
                                               Invitation.expires_at > utcnow()).order_by(Invitation.created_at.desc()).all()
    return ok([_inv_dict(i) for i in rows])


def _send_invite(inv: Invitation, token: str) -> None:
    email_service.send_template("team_invitation", inv.email, {
        "inviter": g.user.name, "workspace": g.workspace.name, "role": inv.role.name,
        "accept_url": f"{current_app.config['WEB_ORIGIN']}/accept-invite?token={token}"}, workspace_id=g.workspace.id)


@bp.post("/team/invitations")
@protect("team.manage")
def invite():
    d = parse(InviteIn)
    role = _role_or_404(d.role_id)
    if role.key == "owner" or role.rank > _my_rank():
        raise forbidden("You can't invite someone to that role", "rank_too_low")
    if db.session.query(WorkspaceMember).join(User).filter(WorkspaceMember.workspace_id == g.workspace.id, User.email == d.email).first():
        raise conflict("That person is already in this workspace", "already_member")
    check_limit(g.workspace, "users")
    db.session.query(Invitation).filter(Invitation.workspace_id == g.workspace.id, Invitation.email == d.email, Invitation.accepted_at.is_(None),
                                        Invitation.revoked_at.is_(None)).update({"revoked_at": utcnow()})
    token = crypto.random_token(32)
    inv = Invitation(workspace_id=g.workspace.id, email=d.email, role_id=role.id, token_hash=crypto.sha256(token), invited_by=g.user.id,
                     expires_at=utcnow() + dt.timedelta(days=7))
    db.session.add(inv)
    db.session.flush()
    db.session.refresh(inv)
    _send_invite(inv, token)
    audit.record("team.invited", entity_type="invitation", entity_id=inv.id, summary=f"Invited {d.email} as {role.name}", after={"email": d.email, "role": role.key})
    analytics.track("invitation_sent")
    db.session.commit()
    body = _inv_dict(inv)
    if current_app.config["ENV"] != "production":
        body["dev_token"] = token
    return created(body)


@bp.delete("/team/invitations/<uuid:iid>")
@protect("team.manage")
def revoke_invitation(iid):
    inv = db.session.query(Invitation).filter_by(id=iid, workspace_id=g.workspace.id).one_or_none()
    if inv is None:
        raise not_found("Invitation")
    inv.revoked_at = utcnow()
    audit.record("team.invitation_revoked", entity_type="invitation", entity_id=inv.id, summary=f"Revoked invitation for {inv.email}")
    db.session.commit()
    return no_content()


# ---- roles ------------------------------------------------------------------------------

@bp.get("/roles")
@protect("team.read")
def list_roles():
    return ok([r.to_dict() for r in _available_roles()])


@bp.get("/permissions")
@protect("team.read")
def list_permissions():
    rows = db.session.query(Permission).order_by(Permission.group, Permission.key).all()
    return ok([r.to_dict() for r in rows])


class RoleIn(Schema):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    permissions: list[str] = Field(default_factory=list)


def _clean_perms(perms: list[str]) -> list[str]:
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        raise ApiError(422, "validation_error", f"Unknown permissions: {', '.join(bad)}", {"permissions": "Unknown permission"})
    mine = g.permissions
    if "*" not in mine and (not set(perms) <= mine):
        raise forbidden("You can't grant permissions you don't have", "rank_too_low")
    return sorted(set(perms))


@bp.post("/roles")
@protect("roles.manage", feature="advanced_permissions")
def create_role():
    d = parse(RoleIn)
    key = "custom_" + uuid.uuid4().hex[:8]
    r = Role(workspace_id=g.workspace.id, key=key, name=d.name, description=d.description, permissions=_clean_perms(d.permissions), rank=30)
    db.session.add(r)
    db.session.flush()
    audit.record("role.created", entity_type="role", entity_id=r.id, summary=f"Created role “{r.name}”", after=r.to_dict())
    db.session.commit()
    return created(r.to_dict())


@bp.patch("/roles/<uuid:rid>")
@protect("roles.manage", feature="advanced_permissions")
def update_role(rid):
    r = _role_or_404(rid)
    if r.is_system or r.workspace_id != g.workspace.id:
        raise forbidden("System roles can't be edited. Create a custom role instead.", "system_role")
    d = parse(RoleIn)
    before = r.to_dict()
    r.name, r.description, r.permissions = d.name, d.description, _clean_perms(d.permissions)
    audit.record("role.updated", entity_type="role", entity_id=r.id, summary=f"Updated role “{r.name}”", before=before, after=r.to_dict())
    db.session.commit()
    return ok(r.to_dict())


@bp.delete("/roles/<uuid:rid>")
@protect("roles.manage", feature="advanced_permissions")
def delete_role(rid):
    r = _role_or_404(rid)
    if r.is_system or r.workspace_id != g.workspace.id:
        raise forbidden("System roles can't be deleted", "system_role")
    if db.session.query(WorkspaceMember).filter_by(role_id=r.id).first() or db.session.query(Invitation).filter_by(role_id=r.id, accepted_at=None, revoked_at=None).first():
        raise conflict("Reassign everyone with this role first", "role_in_use")
    audit.record("role.deleted", entity_type="role", entity_id=r.id, summary=f"Deleted role “{r.name}”")
    db.session.delete(r)
    db.session.commit()
    return no_content()


# ---- teams ------------------------------------------------------------------------------

class TeamIn(Schema):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)


@bp.get("/teams")
@protect("team.read")
def list_teams():
    counts = dict(db.session.query(WorkspaceMember.team_id, func.count()).filter(WorkspaceMember.workspace_id == g.workspace.id).group_by(WorkspaceMember.team_id).all())
    return ok([{**t.to_dict(), "members": counts.get(t.id, 0)} for t in db.session.query(Team).filter_by(workspace_id=g.workspace.id).order_by(Team.name)])


@bp.post("/teams")
@protect("team.manage")
def create_team():
    d = parse(TeamIn)
    t = Team(workspace_id=g.workspace.id, **d.model_dump())
    db.session.add(t)
    db.session.commit()
    return created({**t.to_dict(), "members": 0})


@bp.patch("/teams/<uuid:tid>")
@protect("team.manage")
def update_team(tid):
    t = db.session.query(Team).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Team")
    d = parse(TeamIn)
    t.name, t.description = d.name, d.description
    db.session.commit()
    return ok(t.to_dict())


@bp.delete("/teams/<uuid:tid>")
@protect("team.manage")
def delete_team(tid):
    t = db.session.query(Team).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Team")
    db.session.delete(t)
    db.session.commit()
    return no_content()


# ---- audit log (workspace scope) --------------------------------------------------------

@bp.get("/audit-logs")
@protect("audit.read")
def audit_logs():
    q = db.session.query(AuditLog).filter(AuditLog.workspace_id == g.workspace.id)
    a = request.args
    if a.get("action"):
        q = q.filter(AuditLog.action.ilike(f"%{a['action']}%"))
    if a.get("entity_type"):
        q = q.filter(AuditLog.entity_type == a["entity_type"])
    if a.get("actor_id"):
        q = q.filter(AuditLog.actor_id == a["actor_id"])
    if a.get("q"):
        q = q.filter(or_(AuditLog.summary.ilike(f"%{a['q']}%"), AuditLog.actor_label.ilike(f"%{a['q']}%")))
    if parse_date(a.get("from")):
        q = q.filter(AuditLog.created_at >= parse_date(a.get("from")))
    if parse_date(a.get("to"), end=True):
        q = q.filter(AuditLog.created_at <= parse_date(a.get("to"), end=True))
    page, per = max(int(a.get("page", 1)), 1), min(int(a.get("per_page", 50)), MAX_PER_PAGE)
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).limit(per).offset((page - 1) * per).all()
    return ok([r.to_dict(exclude=("user_agent",)) for r in rows], {"page": page, "per_page": per, "total": total, "pages": max((total + per - 1) // per, 1)})
