"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Lock, MailPlus, Plus, Trash2, UserX } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Button, Checkbox, ConfirmDialog, Dialog, DialogContent, DialogFooter, DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger, Field, Input, NativeSelect, Select, Skeleton, Table, TD, TH, THead, TR, Textarea, cn, formatDate, timeAgo, useToast } from "@crm/ui";
import { MoreHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { INDUSTRIES, COMPANY_SIZES } from "@/lib/constants";
import { useAccess, useMe, useRoles, keys } from "@/lib/queries";
import type { Me, Member, Role } from "@/lib/types";
import { Divided, FieldRow, SettingsSection } from "./ui";

export function WorkspaceSettings() {
  const { data: me } = useMe(); const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess(); const w = me?.workspace;
  const [f, setF] = React.useState({ name: "", industry: "", company_size: "", website: "", timezone: "Asia/Kolkata", currency: "INR", brand_color: "#4f46e5", logo_url: "" }); const [busy, setBusy] = React.useState(false); const [del, setDel] = React.useState(false);
  React.useEffect(() => { if (w) setF({ name: w.name, industry: w.industry ?? "", company_size: w.company_size ?? "", website: w.website ?? "", timezone: w.timezone, currency: w.currency, brand_color: w.brand_color ?? "#4f46e5", logo_url: w.logo_url ?? "" }); }, [w?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => { setBusy(true); try { const nw = await api.patch<Me["workspace"]>("/api/v1/workspace", { ...f, industry: f.industry || null, website: f.website || null, logo_url: f.logo_url || null }); qc.setQueryData<Me>(keys.me, (m) => (m ? { ...m, workspace: nw } : m)); toast.success("Workspace updated"); } catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); } };
  if (!w) return <Skeleton className="h-96" />; const ro = !can("settings.manage");
  return (
    <div className="space-y-6">
      <SettingsSection title="Workspace profile" actions={<Button onClick={save} loading={busy} disabled={ro || !f.name.trim()}>Save changes</Button>}>
        <Divided>
          <FieldRow label="Workspace name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} disabled={ro} /></FieldRow>
          <FieldRow label="Industry"><NativeSelect value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} disabled={ro}><option value="">Select…</option>{INDUSTRIES.map((i) => <option key={i}>{i}</option>)}</NativeSelect></FieldRow>
          <FieldRow label="Company size"><NativeSelect value={f.company_size} onChange={(e) => setF({ ...f, company_size: e.target.value })} disabled={ro}><option value="">Select…</option>{COMPANY_SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></FieldRow>
          <FieldRow label="Website"><Input value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://" disabled={ro} /></FieldRow>
          <FieldRow label="Default currency"><NativeSelect value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })} disabled={ro}>{["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD"].map((c) => <option key={c}>{c}</option>)}</NativeSelect></FieldRow>
          <FieldRow label="Time zone"><NativeSelect value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.target.value })} disabled={ro}>{["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney", "UTC"].map((c) => <option key={c}>{c}</option>)}</NativeSelect></FieldRow>
        </Divided>
      </SettingsSection>
      <SettingsSection title="Branding" description="Shown in the workspace switcher and on invoices and emails."><Divided>
        <FieldRow label="Logo URL" hint="Square image, hosted on https."><div className="flex items-center gap-3"><Avatar name={f.name} src={f.logo_url || undefined} size={40} square /><Input value={f.logo_url} onChange={(e) => setF({ ...f, logo_url: e.target.value })} placeholder="https://…/logo.png" disabled={ro} /></div></FieldRow>
        <FieldRow label="Brand color"><div className="flex items-center gap-3"><input type="color" value={f.brand_color} onChange={(e) => setF({ ...f, brand_color: e.target.value })} disabled={ro} className="size-9 cursor-pointer rounded-md border border-border bg-surface p-1" aria-label="Brand color" /><code className="text-xs text-fg-muted">{f.brand_color}</code></div></FieldRow></Divided>
        <p className="mt-2 text-xs text-fg-subtle">Save changes above to apply branding.</p></SettingsSection>
      {me?.role?.key === "owner" && <SettingsSection title="Danger zone" description="These actions are permanent."><div className="flex items-center justify-between gap-4"><div><p className="text-sm font-medium">Delete this workspace</p><p className="text-xs text-fg-muted">Everyone loses access. Export your data first from Data settings.</p></div><Button variant="danger-soft" onClick={() => setDel(true)}>Delete workspace</Button></div></SettingsSection>}
      <ConfirmDialog open={del} onOpenChange={setDel} title="Delete workspace?" typeToConfirm={w.name} confirmLabel="Delete workspace" description="All members will lose access. The data is retained for a short recovery window, then purged." onConfirm={async () => { await api.raw("DELETE", "/api/v1/workspace", { confirm_name: w.name }).then(async (r) => { if (!r.ok) throw new Error((await r.json()).error?.message); }); window.location.href = "/login"; }} />
    </div>
  );
}

export function TeamSettings() {
  const { data: me } = useMe(); const qc = useQueryClient(); const toast = useToast(); const { can, has } = useAccess(); const roles = useRoles(); const manage = can("team.manage");
  const members = useQuery({ queryKey: ["members", "full"], queryFn: () => api.get<Member[]>("/api/v1/team/members") });
  const invites = useQuery({ queryKey: ["invites"], enabled: manage, queryFn: () => api.get<{ id: string; email: string; role: { name: string }; expires_at: string }[]>("/api/v1/team/invitations") });
  const teams = useQuery({ queryKey: ["teams"], queryFn: () => api.get<{ id: string; name: string; description: string | null; members: number }[]>("/api/v1/teams") });
  const [inv, setInv] = React.useState(false); const [email, setEmail] = React.useState(""); const [roleId, setRoleId] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [link, setLink] = React.useState<string | null>(null);
  const [rm, setRm] = React.useState<Member | null>(null); const [teamName, setTeamName] = React.useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["members"] }); qc.invalidateQueries({ queryKey: ["invites"] }); qc.invalidateQueries({ queryKey: ["teams"] }); };
  const patch = async (m: Member, body: Record<string, unknown>, msg: string) => { try { await api.patch(`/api/v1/team/members/${m.id}`, body); refresh(); toast.success(msg); } catch (e) { toast.error("Couldn't update", (e as Error).message); } };
  const invite = async () => { setBusy(true); setErr(null); try { const r = await api.post<{ dev_token?: string }>("/api/v1/team/invitations", { email, role_id: roleId }); refresh(); toast.success("Invitation sent", email); if (r.dev_token) setLink(`${window.location.origin}/accept-invite?token=${r.dev_token}`); else setInv(false); setEmail(""); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const assignable = (roles.data ?? []).filter((r) => r.key !== "owner" && r.rank <= (members.data?.find((m) => m.user_id === me?.user.id)?.role.rank ?? 0));
  React.useEffect(() => { if (!roleId && assignable.length) setRoleId(assignable.find((r) => r.key === "sales_rep")?.id ?? assignable[0].id); }, [assignable.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const lim = me?.limits?.users; const count = (members.data?.filter((m) => m.status === "active").length ?? 0) + (invites.data?.length ?? 0);
  return (
    <div className="space-y-6">
      <SettingsSection title="Team members" description={`${count}${lim ? ` of ${lim}` : ""} seats used.`} actions={manage && <Button onClick={() => { setInv(true); setLink(null); setErr(null); }}><MailPlus /> Invite</Button>}>
        {members.isLoading ? <Skeleton className="h-40" /> : <div className="-mx-5 overflow-x-auto"><Table><THead><TR><TH className="pl-5">Member</TH><TH>Role</TH><TH>Last sign-in</TH><TH>2FA</TH><TH /></TR></THead><tbody>
          {members.data!.map((m) => { const self = m.user_id === me?.user.id; return (
            <TR key={m.id}><TD className="pl-5"><div className="flex items-center gap-3"><Avatar name={m.name} size={34} /><div><p className="font-medium">{m.name} {self && <span className="text-xs text-fg-subtle">(you)</span>}{m.status === "disabled" && <Badge tone="neutral" className="ml-1">Disabled</Badge>}</p><p className="text-xs text-fg-muted">{m.email}</p></div></div></TD>
              <TD>{manage && m.role.key !== "owner" && !self ? <div className="w-44"><Select size="sm" value={m.role.id} onValueChange={(v) => patch(m, { role_id: v }, "Role updated")} options={assignable.map((r) => ({ value: r.id, label: r.name }))} /></div> : <Badge tone={m.role.key === "owner" ? "primary" : "neutral"}>{m.role.name}</Badge>}</TD>
              <TD className="text-[13px] text-fg-muted">{m.last_login_at ? timeAgo(m.last_login_at) : "Never"}</TD><TD>{m.mfa_enabled ? <Badge tone="success">On</Badge> : <span className="text-xs text-fg-subtle">Off</span>}</TD>
              <TD className="pr-5 text-right">{manage && m.role.key !== "owner" && !self && <DropdownMenu><DropdownTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={`Actions for ${m.name}`}><MoreHorizontal /></Button></DropdownTrigger><DropdownContent><DropdownItem onSelect={() => patch(m, { status: m.status === "active" ? "disabled" : "active" }, m.status === "active" ? "Member disabled" : "Member enabled")}>{m.status === "active" ? "Disable access" : "Re-enable access"}</DropdownItem><DropdownSeparator /><DropdownItem danger icon={<UserX />} onSelect={() => setRm(m)}>Remove from workspace</DropdownItem></DropdownContent></DropdownMenu>}</TD></TR>); })}</tbody></Table></div>}
        {manage && !!invites.data?.length && <div className="mt-6"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-subtle">Pending invitations</p><ul className="divide-y divide-border rounded-lg border border-border">{invites.data.map((i) => <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm"><span><span className="font-medium">{i.email}</span> <span className="text-fg-muted">· {i.role.name} · expires {formatDate(i.expires_at)}</span></span><Button size="xs" variant="ghost" onClick={async () => { await api.delete(`/api/v1/team/invitations/${i.id}`); refresh(); toast.success("Invitation revoked"); }}>Revoke</Button></li>)}</ul></div>}
      </SettingsSection>
      <SettingsSection title="Teams" description="Group people (e.g. Sales, Success) for reporting.">
        <ul className="divide-y divide-border">{teams.data?.map((t) => <li key={t.id} className="flex items-center justify-between py-3 text-sm"><span><span className="font-medium">{t.name}</span> <span className="text-fg-muted">· {t.members} member{t.members === 1 ? "" : "s"}</span></span>{manage && <Button size="icon-sm" variant="ghost" aria-label={`Delete ${t.name}`} onClick={async () => { await api.delete(`/api/v1/teams/${t.id}`); refresh(); }}><Trash2 /></Button>}</li>)}{teams.data?.length === 0 && <li className="py-3 text-sm text-fg-muted">No teams yet.</li>}</ul>
        {manage && <form className="mt-3 flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!teamName.trim()) return; await api.post("/api/v1/teams", { name: teamName.trim() }); setTeamName(""); refresh(); }}><Input value={teamName} onChange={(e) => setTeamName(e.target.value)} placeholder="New team name" aria-label="Team name" /><Button type="submit" variant="secondary" disabled={!teamName.trim()}><Plus /> Add team</Button></form>}
      </SettingsSection>
      <Dialog open={inv} onOpenChange={setInv}><DialogContent size="sm" title="Invite a teammate" description="They'll get an email with a link to join.">
        {link ? <div className="space-y-3"><p className="text-sm text-fg-muted">Invitation created. In development no email provider is configured — share this link:</p><div className="flex gap-2 rounded-lg border border-border bg-bg-subtle p-2"><code className="min-w-0 flex-1 truncate text-xs">{link}</code><Button size="xs" variant="ghost" onClick={() => { navigator.clipboard?.writeText(link); toast.success("Copied"); }}><Copy /></Button></div><DialogFooter><Button onClick={() => setInv(false)}>Done</Button></DialogFooter></div> : <>
          <div className="space-y-4"><Field label="Email" error={err ?? undefined}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus placeholder="teammate@company.com" /></Field><Field label="Role"><NativeSelect value={roleId} onChange={(e) => setRoleId(e.target.value)}>{assignable.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</NativeSelect></Field></div>
          <DialogFooter><Button variant="secondary" onClick={() => setInv(false)}>Cancel</Button><Button onClick={invite} loading={busy} disabled={!email.includes("@")}>Send invitation</Button></DialogFooter></>}</DialogContent></Dialog>
      <ConfirmDialog open={!!rm} onOpenChange={(o) => !o && setRm(null)} title={`Remove ${rm?.name}?`} description="They'll lose access immediately. Their leads, deals and tasks are reassigned to you." confirmLabel="Remove" onConfirm={async () => { await api.delete(`/api/v1/team/members/${rm!.id}`); refresh(); toast.success("Member removed"); }} />
      {!has("advanced_permissions") && <p className="text-center text-xs text-fg-subtle">Custom roles need the Business plan. <Link href="/app/billing" className="text-primary hover:underline">See plans</Link></p>}
    </div>
  );
}

export function RolesSettings() {
  const { has, can } = useAccess(); const toast = useToast(); const qc = useQueryClient(); const roles = useRoles();
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api.get<{ key: string; group: string; description: string }[]>("/api/v1/permissions") });
  const [edit, setEdit] = React.useState<Partial<Role> | null>(null); const [sel, setSel] = React.useState<Set<string>>(new Set()); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null); const [view, setView] = React.useState<Role | null>(null);
  const groups = React.useMemo(() => { const g: Record<string, { key: string; description: string }[]> = {}; perms.data?.forEach((p) => (g[p.group] ??= []).push(p)); return g; }, [perms.data]);
  const open = (r?: Role) => { setEdit(r ?? { name: "", description: "", permissions: [] }); setSel(new Set(r?.permissions ?? ["leads.read", "contacts.read", "companies.read", "deals.read"])); setErr(null); };
  const save = async () => { setBusy(true); setErr(null); try { const body = { name: edit!.name, description: edit!.description, permissions: [...sel] }; edit!.id ? await api.patch(`/api/v1/roles/${edit!.id}`, body) : await api.post("/api/v1/roles", body); qc.invalidateQueries({ queryKey: ["roles"] }); setEdit(null); toast.success("Role saved"); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const manage = can("roles.manage") && has("advanced_permissions");
  const has2 = (r: Role, p: string) => r.permissions.includes("*") || r.permissions.includes(p);
  return (
    <SettingsSection title="Roles & permissions" description="What each role can do. System roles are fixed; create custom roles on the Business plan." actions={<Button onClick={() => open()} disabled={!manage}>{manage ? <Plus /> : <Lock />} Custom role</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">{roles.data?.map((r) => <div key={r.id} className="rounded-xl border border-border p-4"><div className="flex items-start justify-between gap-2"><div><p className="font-semibold">{r.name} {r.is_system ? <Badge tone="neutral" className="ml-1">System</Badge> : <Badge tone="primary" className="ml-1">Custom</Badge>}</p><p className="mt-0.5 text-[13px] text-fg-muted">{r.description}</p></div></div><div className="mt-3 flex gap-2"><Button size="xs" variant="secondary" onClick={() => setView(r)}>View permissions</Button>{!r.is_system && manage && <><Button size="xs" variant="ghost" onClick={() => open(r)}>Edit</Button><Button size="xs" variant="ghost" className="text-danger" onClick={async () => { try { await api.delete(`/api/v1/roles/${r.id}`); qc.invalidateQueries({ queryKey: ["roles"] }); } catch (e) { toast.error("Can't delete", (e as Error).message); } }}>Delete</Button></>}</div></div>)}</div>
      <Dialog open={!!view} onOpenChange={(o) => !o && setView(null)}><DialogContent size="lg" title={`${view?.name} permissions`}>{view && <div className="grid gap-5 sm:grid-cols-2">{Object.entries(groups).map(([g, ps]) => <div key={g}><p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-fg-subtle">{g}</p><ul className="space-y-1">{ps.map((p) => <li key={p.key} className={cn("flex items-center gap-2 text-[13px]", has2(view, p.key) ? "" : "text-fg-subtle line-through")}><span className={cn("size-1.5 rounded-full", has2(view, p.key) ? "bg-success" : "bg-border-strong")} />{p.description} <code className="ml-auto text-[11px] text-fg-subtle no-underline">{p.key}</code></li>)}</ul></div>)}</div>}</DialogContent></Dialog>
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}><DialogContent size="lg" title={edit?.id ? "Edit role" : "New custom role"}>
        {edit && <div className="space-y-5"><div className="grid gap-4 sm:grid-cols-2"><Field label="Role name"><Input value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field><Field label="Description"><Input value={edit.description ?? ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field></div>
          <div className="grid gap-5 sm:grid-cols-2">{Object.entries(groups).map(([g, ps]) => <fieldset key={g}><legend className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-fg-subtle">{g}</legend><ul className="space-y-1.5">{ps.map((p) => <li key={p.key}><label className="flex cursor-pointer items-center gap-2.5 text-[13px]"><Checkbox checked={sel.has(p.key)} onCheckedChange={(c) => setSel((s) => { const n = new Set(s); c ? n.add(p.key) : n.delete(p.key); return n; })} />{p.description}</label></li>)}</ul></fieldset>)}</div>{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>}
        <DialogFooter><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button onClick={save} loading={busy} disabled={!edit?.name?.trim() || sel.size === 0}>Save role</Button></DialogFooter></DialogContent></Dialog>
    </SettingsSection>
  );
}
export { Textarea };
