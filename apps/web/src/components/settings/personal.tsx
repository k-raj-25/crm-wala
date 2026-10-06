"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Laptop, ShieldCheck, ShieldOff } from "lucide-react";
import QRCode from "qrcode";
import * as React from "react";
import { Badge, Button, Dialog, DialogContent, DialogFooter, Field, Input, NativeSelect, Select, Skeleton, Switch, formatDate, timeAgo, useToast, useTheme } from "@crm/ui";
import { api } from "@/lib/api";
import { useMe, usePipelines, keys } from "@/lib/queries";
import type { Me } from "@/lib/types";
import { PasswordInput, StrengthMeter } from "../auth/auth-shell";
import { Divided, FieldRow, SettingsSection } from "./ui";

const TZ = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "Europe/Berlin", "America/New_York", "America/Chicago", "America/Los_Angeles", "Australia/Sydney", "UTC"];

export function ProfileSettings() {
  const { data: me } = useMe(); const qc = useQueryClient(); const toast = useToast(); const { setPref } = useTheme(); const pipelines = usePipelines();
  const u = me?.user; const p = u?.preferences ?? {};
  const [name, setName] = React.useState(""); const [role, setRole] = React.useState(""); const [phone, setPhone] = React.useState(""); const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (u) { setName(u.name); setRole(u.job_role ?? ""); setPhone(u.phone ?? ""); } }, [u?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async (patch: Record<string, unknown>, msg = "Saved") => { setBusy(true); try { const m = await api.patch<Me>("/api/v1/me/preferences", patch); qc.setQueryData(keys.me, m); toast.success(msg); } catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); } };
  if (!u) return <Skeleton className="h-96" />;
  return (
    <div className="space-y-6">
      <SettingsSection title="Profile" description="How you appear to your teammates." actions={<Button onClick={() => save({ name, job_role: role || null, phone: phone || null }, "Profile updated")} loading={busy} disabled={!name.trim()}>Save</Button>}>
        <Divided><FieldRow label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></FieldRow><FieldRow label="Email" hint="Contact support to change your sign-in email."><Input value={u.email} disabled /></FieldRow><FieldRow label="Job title"><Input value={role} onChange={(e) => setRole(e.target.value)} /></FieldRow><FieldRow label="Phone"><Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></FieldRow></Divided>
      </SettingsSection>
      <SettingsSection title="Preferences" description="Personalise how CRM Wala looks and formats data for you.">
        <Divided>
          <FieldRow label="Theme"><Select value={p.theme ?? "system"} onValueChange={(v) => { setPref(v as "light" | "dark" | "system"); save({ theme: v }); }} options={[{ value: "system", label: "Match my device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} /></FieldRow>
          <FieldRow label="Date format"><Select value={p.date_format ?? "DD/MM/YYYY"} onValueChange={(v) => save({ date_format: v })} options={["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"].map((v) => ({ value: v, label: v }))} /></FieldRow>
          <FieldRow label="Currency" hint="Default for new deals."><Select value={p.currency ?? me?.workspace?.currency ?? "INR"} onValueChange={(v) => save({ currency: v })} options={["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD"].map((v) => ({ value: v, label: v }))} /></FieldRow>
          <FieldRow label="Time zone"><Select value={p.timezone ?? me?.workspace?.timezone ?? "Asia/Kolkata"} onValueChange={(v) => save({ timezone: v })} options={TZ.map((v) => ({ value: v, label: v.replace("_", " ") }))} /></FieldRow>
          <FieldRow label="Language" hint="More languages are coming soon."><Select value="en" onValueChange={() => {}} options={[{ value: "en", label: "English" }]} /></FieldRow>
          {(pipelines.data?.length ?? 0) > 0 && <FieldRow label="Default pipeline"><Select value={p.default_pipeline_id ?? pipelines.data!.find((x) => x.is_default)?.id} onValueChange={(v) => save({ default_pipeline_id: v })} options={pipelines.data!.map((x) => ({ value: x.id, label: x.name }))} /></FieldRow>}
        </Divided>
      </SettingsSection>
    </div>
  );
}

export function NotificationSettings() {
  const toast = useToast();
  const q = useQuery({ queryKey: ["notif-prefs"], queryFn: () => api.get<{ type: string; label: string; in_app: boolean; email: boolean }[]>("/api/v1/me/notification-preferences") });
  const set = async (type: string, ch: "in_app" | "email", v: boolean) => {
    const rows = q.data!.map((r) => (r.type === type ? { ...r, [ch]: v } : r));
    try { await api.put("/api/v1/me/notification-preferences", { prefs: Object.fromEntries(rows.map((r) => [r.type, { in_app: r.in_app, email: r.email }])) }); q.refetch(); } catch (e) { toast.error("Couldn't save", (e as Error).message); }
  };
  return (
    <SettingsSection title="Notifications" description="Choose how you want to hear about activity. Payment and security alerts to owners can't be fully disabled.">
      {q.isLoading ? <Skeleton className="h-64" /> : (
        <div><div className="grid grid-cols-[1fr_72px_72px] gap-2 border-b border-border pb-2 text-xs font-medium uppercase tracking-wide text-fg-subtle"><span /><span className="text-center">In-app</span><span className="text-center">Email</span></div>
          {q.data!.map((r) => <div key={r.type} className="grid grid-cols-[1fr_72px_72px] items-center gap-2 border-b border-border py-3.5 last:border-0"><span className="text-sm font-medium">{r.label}</span><span className="flex justify-center"><Switch checked={r.in_app} onCheckedChange={(v) => set(r.type, "in_app", v)} aria-label={`${r.label} in-app`} /></span><span className="flex justify-center"><Switch checked={r.email} onCheckedChange={(v) => set(r.type, "email", v)} aria-label={`${r.label} email`} /></span></div>)}</div>)}
    </SettingsSection>
  );
}

function TwoFactor() {
  const { data: me } = useMe(); const qc = useQueryClient(); const toast = useToast();
  const [setup, setSetup] = React.useState<{ secret: string; qr: string } | null>(null); const [code, setCode] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const [dis, setDis] = React.useState(false); const [pw, setPw] = React.useState("");
  const start = async () => { const r = await api.post<{ secret: string; otpauth_uri: string }>("/api/v1/auth/2fa/setup"); setSetup({ secret: r.secret, qr: await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 192 }) }); setCode(""); setErr(null); };
  const enable = async () => { setBusy(true); setErr(null); try { await api.post("/api/v1/auth/2fa/enable", { code }); qc.invalidateQueries({ queryKey: keys.me }); setSetup(null); toast.success("Two-factor authentication enabled"); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const disable = async () => { setBusy(true); setErr(null); try { await api.post("/api/v1/auth/2fa/disable", { password: pw, code }); qc.invalidateQueries({ queryKey: keys.me }); setDis(false); toast.success("Two-factor authentication disabled"); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const on = me?.user.mfa_enabled;
  return (
    <SettingsSection title="Two-factor authentication" description="Protect your account with a code from an authenticator app (Google Authenticator, 1Password, Authy)." actions={on ? <Button variant="danger-soft" onClick={() => { setDis(true); setCode(""); setPw(""); setErr(null); }}><ShieldOff /> Disable</Button> : <Button onClick={start}><ShieldCheck /> Set up</Button>}>
      <p className="flex items-center gap-2 text-sm">{on ? <Badge tone="success" dot>Enabled</Badge> : <Badge tone="neutral" dot>Not enabled</Badge>}<span className="text-fg-muted">{on ? "You'll be asked for a code each time you sign in." : "Recommended for owners and admins."}</span></p>
      <Dialog open={!!setup} onOpenChange={(o) => !o && setSetup(null)}><DialogContent size="sm" title="Set up authenticator" description="Scan the QR code, then enter the 6-digit code.">
        {setup && <div className="space-y-4"><div className="flex justify-center rounded-xl bg-white p-3"><img src={setup.qr} alt="QR code for your authenticator app" width={192} height={192} /></div><p className="text-center text-xs text-fg-muted">Can't scan? Enter this key: <code className="select-all font-mono text-fg">{setup.secret}</code></p>
          <Field label="Verification code" error={err ?? undefined}><Input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="text-center text-lg tracking-[0.4em]" autoFocus /></Field></div>}
        <DialogFooter><Button variant="secondary" onClick={() => setSetup(null)}>Cancel</Button><Button onClick={enable} loading={busy} disabled={code.length < 6}><Check /> Enable</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={dis} onOpenChange={setDis}><DialogContent size="sm" title="Disable two-factor?" description="Enter your password and a current code to confirm.">
        <div className="space-y-4"><Field label="Password"><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></Field><Field label="Authentication code" error={err ?? undefined}><Input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field></div>
        <DialogFooter><Button variant="secondary" onClick={() => setDis(false)}>Cancel</Button><Button variant="danger" onClick={disable} loading={busy} disabled={!pw || code.length < 6}>Disable</Button></DialogFooter></DialogContent></Dialog>
    </SettingsSection>
  );
}

export function SecuritySettings() {
  const toast = useToast(); const qc = useQueryClient();
  const [cur, setCur] = React.useState(""); const [next, setNext] = React.useState(""); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<Record<string, string>>({});
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<{ id: string; ip: string; user_agent: string; created_at: string; current: boolean }[]>("/api/v1/auth/sessions") });
  const change = async () => { setBusy(true); setErr({}); try { await api.post("/api/v1/auth/change-password", { current_password: cur, new_password: next }); setCur(""); setNext(""); toast.success("Password changed", "Other devices have been signed out."); qc.invalidateQueries({ queryKey: ["sessions"] }); } catch (e) { const d = (e as { details?: Record<string, string> }).details; setErr(d ?? { new_password: (e as Error).message }); } finally { setBusy(false); } };
  const device = (ua: string) => (/iPhone|Android/.test(ua) ? "Mobile" : /Mac/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows PC" : "Browser") + (/Chrome\//.test(ua) ? " · Chrome" : /Firefox/.test(ua) ? " · Firefox" : /Safari/.test(ua) ? " · Safari" : "");
  return (
    <div className="space-y-6">
      <SettingsSection title="Password" actions={<Button onClick={change} loading={busy} disabled={!cur || next.length < 10}>Update password</Button>}>
        <Divided><FieldRow label="Current password"><Field error={err.current_password}><PasswordInput value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></Field></FieldRow>
          <FieldRow label="New password" hint="At least 10 characters with letters and numbers."><Field error={err.new_password}><PasswordInput value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field><StrengthMeter value={next} /></FieldRow></Divided>
      </SettingsSection>
      <TwoFactor />
      <SettingsSection title="Active sessions" description="Devices currently signed in to your account.">
        {sessions.isLoading ? <Skeleton className="h-24" /> : <ul className="divide-y divide-border">{sessions.data?.map((s) => <li key={s.id} className="flex items-center gap-3 py-3.5"><Laptop className="size-5 text-fg-subtle" /><div className="min-w-0 flex-1"><p className="text-sm font-medium">{device(s.user_agent ?? "")} {s.current && <Badge tone="success">This device</Badge>}</p><p className="text-xs text-fg-muted">{s.ip} · signed in {timeAgo(s.created_at)}</p></div>{!s.current && <Button size="sm" variant="secondary" onClick={async () => { await api.delete(`/api/v1/auth/sessions/${s.id}`); sessions.refetch(); toast.success("Session revoked"); }}>Sign out</Button>}</li>)}</ul>}
      </SettingsSection>
    </div>
  );
}
export { NativeSelect, formatDate };
