"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, Check, Clipboard, PhoneCall, PhoneIncoming, PhoneOutgoing, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Button, Dialog, DialogContent, DialogFooter, Field, Input, NativeSelect, Skeleton, Switch, cn, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess, useMembers } from "@/lib/queries";

type Status = { enabled: boolean; provider: string | null; my_phone_set: boolean; can_transfer_inbound: boolean; can_transfer_outbound: boolean };
export type LiveCall = { id: string; direction: "inbound" | "outbound"; status: "ringing" | "in_progress"; started_at: string; answered_at: string | null; phone: string | null; record: { type: "lead" | "contact"; id: string; name: string } | null; can_transfer: boolean; pending_transfer: { to: string; name: string } | null; transferred_from: string | null };
type Target = { user_id: string; name: string; role: string; avatar_url: string | null; has_phone: boolean };
type ProviderField = { key: string; label: string; hint?: string; secret?: boolean; optional?: boolean; options?: { value: string; label: string }[]; value?: string | null };
type Routing = { inbound: "lead_owner" | "fallback"; fallback_user_id: string | null; ring_fallback_too: boolean; create_leads: boolean; record: boolean; ring_seconds: number; client_first: boolean; greeting: boolean };
export type CallingSettings = { provider: string; account_label: string; hooks: { key: string; label: string; url: string }[]; routing: Routing; has_flow: boolean; fields: ProviderField[] };

export const useCalling = () => useQuery({ queryKey: ["calling-status"], staleTime: 60_000, retry: false, queryFn: () => api.get<Status>("/api/v1/calling/status") });

/** True when this member should call through the company number instead of dialling the client's phone directly. */
export function useCanCall() {
  const { can } = useAccess(); const s = useCalling();
  return !!s.data?.enabled && can("calls.place");
}

/** "Call" through the company number: rings the member's own phone, then the client. Neither sees the other's number. */
export function CallButton({ entity, id, name, size = "md", variant = "secondary", iconOnly, className }: { entity: "lead" | "contact"; id: string; name: string; size?: "xs" | "sm" | "md"; variant?: "secondary" | "primary" | "ghost"; iconOnly?: boolean; className?: string }) {
  const qc = useQueryClient(); const toast = useToast(); const s = useCalling(); const ok = useCanCall();
  const [busy, setBusy] = React.useState(false);
  if (!ok) return null;
  const call = async () => {
    if (!s.data?.my_phone_set) { toast.toast({ tone: "warning", title: "Add your mobile number first", description: "Settings → Profile → Phone. The CRM rings you on it, then connects the client." }); return; }
    setBusy(true);
    try {
      await api.post("/api/v1/calling/call", { [`${entity}_id`]: id });
      toast.toast({ tone: "info", title: "Ringing your phone", description: "Pick up and we'll connect the client. They see the company number, not yours." });
      qc.invalidateQueries({ queryKey: ["live-calls"] });
    } catch (e) { toast.error("Couldn't start the call", (e as Error).message); } finally { setBusy(false); }
  };
  const btnSize = iconOnly ? (size === "xs" ? "icon-xs" : size === "sm" ? "icon-sm" : "icon") : size;
  return <Button size={btnSize} variant={variant} loading={busy} onClick={call} className={className} aria-label={`Call ${name} from the company number`} title="Call from the company number"><PhoneCall />{!iconOnly && <span className={size === "md" ? "hidden sm:inline" : undefined}>Call</span>}</Button>;
}

function useTicker(on: boolean) {
  const [, set] = React.useState(0);
  React.useEffect(() => { if (!on) return; const t = setInterval(() => set((n) => n + 1), 1000); return () => clearInterval(t); }, [on]);
}
const clock = (from: string) => { const s = Math.max(0, Math.floor((Date.now() - new Date(from).getTime()) / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

/** Floating card for the member's live call (bottom right), with the hand-over picker. Polls while calling is set up. */
export function LiveCalls() {
  const ok = useCanCall();
  const q = useQuery({ queryKey: ["live-calls"], enabled: ok, refetchInterval: (x) => (x.state.status === "error" ? 30_000 : (x.state.data?.length ? 3_000 : 8_000)), queryFn: () => api.get<LiveCall[]>("/api/v1/calling/active") });
  const [hidden, setHidden] = React.useState<string[]>([]);
  const calls = (q.data ?? []).filter((c) => !hidden.includes(c.id));
  useTicker(calls.length > 0);
  if (!ok || !calls.length) return null;
  return (
    <div className="pointer-events-none fixed inset-x-3 bottom-[calc(208px+env(safe-area-inset-bottom))] z-40 flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6 md:bottom-[88px]" aria-live="polite">
      {calls.map((c) => <LiveCallCard key={c.id} c={c} onHide={() => setHidden((h) => [...h, c.id])} />)}
    </div>
  );
}

function LiveCallCard({ c, onHide }: { c: LiveCall; onHide: () => void }) {
  const qc = useQueryClient(); const toast = useToast();
  const [pick, setPick] = React.useState(false); const [busy, setBusy] = React.useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["live-calls"] });
  const cancel = async () => { setBusy(true); try { await api.delete(`/api/v1/calling/calls/${c.id}/transfer`); refresh(); } catch (e) { toast.error("Couldn't cancel", (e as Error).message); } finally { setBusy(false); } };
  const ringing = c.status === "ringing";
  const Icon = c.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;
  const what = ringing ? (c.direction === "inbound" ? "Incoming call · pick up your phone" : "Ringing your phone…") : `On call · ${clock(c.answered_at ?? c.started_at)}`;
  return (
    <div className="glass-pop pointer-events-auto w-full max-w-sm rounded-2xl border border-border p-4 shadow-lg sm:w-80" role="status">
      <div className="flex items-start gap-3">
        <span className={cn("relative grid size-10 shrink-0 place-items-center rounded-full", ringing ? "bg-primary-soft text-primary" : "bg-success-soft text-success")}>
          {ringing && <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" />}<Icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          {c.record ? <Link href={`/app/${c.record.type === "contact" ? "contacts" : "leads"}/${c.record.id}`} className="block truncate font-semibold hover:text-primary">{c.record.name}</Link> : <p className="truncate font-semibold">{c.phone ?? "Unknown caller"}</p>}
          <p className="tabular text-[13px] text-fg-muted">{what}</p>
          {c.transferred_from && <p className="mt-0.5 text-xs text-fg-subtle">Handed over by {c.transferred_from}</p>}
        </div>
        <button onClick={onHide} aria-label="Hide" title="Hide this card (the call isn't affected)" className="rounded p-1 text-fg-subtle hover:text-fg"><X className="size-4" /></button>
      </div>
      {c.pending_transfer ? (
        <div className="mt-3 rounded-xl bg-warning-soft p-3 text-[13px] text-warning">
          <p><b>Hang up your phone now.</b> {c.pending_transfer.name} will be rung and the client stays on the line.</p>
          <Button size="xs" variant="ghost" className="mt-2" loading={busy} onClick={cancel}>Keep the call</Button>
        </div>
      ) : c.can_transfer && (
        <div className="mt-3 flex justify-end"><Button size="sm" variant="secondary" onClick={() => setPick(true)}><ArrowRightLeft /> Hand over</Button></div>
      )}
      {pick && <TransferDialog call={c} onClose={() => setPick(false)} onDone={refresh} />}
    </div>
  );
}

function TransferDialog({ call, onClose, onDone }: { call: LiveCall; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const q = useQuery({ queryKey: ["transfer-targets", call.id], queryFn: () => api.get<{ any: boolean; targets: Target[] }>(`/api/v1/calling/calls/${call.id}/transfer-targets`) });
  const [busy, setBusy] = React.useState<string | null>(null);
  const go = async (t: Target) => {
    setBusy(t.user_id);
    try { await api.post(`/api/v1/calling/calls/${call.id}/transfer`, { to_user_id: t.user_id }); onDone(); onClose(); toast.toast({ tone: "info", title: `Hang up to hand over to ${t.name.split(" ")[0]}`, description: "The client stays on the line and hears hold music while they're rung." }); }
    catch (e) { toast.error("Couldn't hand over", (e as Error).message); } finally { setBusy(null); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title="Hand over this call" description={q.data?.any ? "Pick anyone in the team. You hang up, they're rung, and the client stays on the line." : "You can hand calls to your manager. You hang up, they're rung, and the client stays on the line."}>
        {q.isLoading ? <Skeleton className="h-32" /> : !q.data?.targets.length ? <p className="text-sm text-fg-muted">There's nobody to hand this call to yet. Ask an admin to set who you report to in Settings → Team.</p> : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {q.data.targets.map((t) => (
              <li key={t.user_id} className="flex items-center gap-3 px-3 py-2.5">
                <Avatar name={t.name} src={t.avatar_url} size={32} />
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{t.name}</p><p className="truncate text-xs text-fg-muted">{t.has_phone ? t.role : "No mobile number on their profile"}</p></div>
                <Button size="sm" variant="secondary" disabled={!t.has_phone || !!busy} loading={busy === t.user_id} onClick={() => go(t)}>Hand over</Button>
              </li>
            ))}
          </ul>
        )}
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---- Integrations: connect + manage --------------------------------------------------------------------------------

export const EXOTEL_FIELDS: ProviderField[] = [
  { key: "account_sid", label: "Account SID", hint: "Exotel dashboard → Settings → API Settings" },
  { key: "api_key", label: "API key" },
  { key: "api_token", label: "API token", secret: true },
  { key: "subdomain", label: "Region", options: [{ value: "api.in.exotel.com", label: "Mumbai (api.in.exotel.com)" }, { value: "api.exotel.com", label: "Singapore (api.exotel.com)" }] },
  { key: "exophone", label: "Company number (ExoPhone)", hint: "The virtual number clients see and call back" },
  { key: "flow_app_id", label: "Call flow app ID", optional: true, hint: "App Bazaar → My Apps: the ID of the CRM flow on your ExoPhone. Needed to ring the client first on outgoing calls." },
];
export const emptyCallingCreds = () => Object.fromEntries(EXOTEL_FIELDS.map((f) => [f.key, f.key === "subdomain" ? "api.in.exotel.com" : ""])) as Record<string, string>;
export const callingCredsReady = (v: Record<string, string>, reconnect: boolean) => reconnect ? Object.entries(v).some(([k, x]) => k !== "subdomain" && x.trim()) : EXOTEL_FIELDS.every((f) => f.optional || !!v[f.key]?.trim());

export function CallingConnectFields({ value, onChange, reconnect }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void; reconnect?: boolean }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-muted">Use your firm's own Exotel account. Every call then goes out from your ExoPhone, so clients never see an employee's number and employees never see the client's.{reconnect && " Leave a field empty to keep the saved value."}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {EXOTEL_FIELDS.map((f) => (
          <Field key={f.key} label={f.label + (f.optional ? " (optional)" : "")} hint={f.hint} className={f.key === "flow_app_id" || f.key === "exophone" ? "sm:col-span-2" : undefined}>
            {f.options ? <NativeSelect value={value[f.key]} onChange={(e) => onChange({ ...value, [f.key]: e.target.value })}>{f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</NativeSelect>
              : <Input type={f.secret ? "password" : "text"} value={value[f.key] ?? ""} onChange={(e) => onChange({ ...value, [f.key]: e.target.value })} autoComplete="off" />}
          </Field>
        ))}
      </div>
    </div>
  );
}

function CopyRow({ label, text }: { label: string; text: string }) {
  const [ok, setOk] = React.useState(false);
  return (
    <Field label={label}>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2"><code className="min-w-0 flex-1 truncate text-xs">{text}</code><Button size="xs" variant="ghost" aria-label={`Copy ${label}`} onClick={() => { navigator.clipboard?.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}>{ok ? <Check /> : <Clipboard />}</Button></div>
    </Field>
  );
}

export function CallingHooks({ hooks, intro }: { hooks: CallingSettings["hooks"]; intro?: boolean }) {
  return (
    <div className="space-y-3">
      {intro && <p className="text-sm">Connected. So callbacks reach the right person, build a call flow for your ExoPhone in <b>Exotel → App Bazaar</b>: a <b>Connect</b> applet using the first URL, then a <b>Passthru</b> applet with the second (200 goes back to Connect, 302 to Hangup).</p>}
      {hooks.map((h) => <CopyRow key={h.key} label={h.label} text={h.url} />)}
    </div>
  );
}

function Row({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <div className="flex items-start justify-between gap-4"><div className="min-w-0"><p className="text-sm font-medium">{title}</p>{hint && <p className="mt-0.5 text-xs text-fg-muted">{hint}</p>}</div><div className="shrink-0">{children}</div></div>;
}

/** Manage view: webhook URLs for the call flow, and who callbacks ring. */
export function CallingManage() {
  const qc = useQueryClient(); const toast = useToast(); const members = useMembers();
  const s = useQuery({ queryKey: ["calling-settings"], queryFn: () => api.get<CallingSettings>("/api/v1/calling/settings") });
  const [busy, setBusy] = React.useState(false);
  if (s.isLoading) return <Skeleton className="h-40 w-full" />;
  if (!s.data) return null;
  const r = s.data.routing;
  const save = async (patch: Partial<Routing>) => {
    setBusy(true);
    try { await api.patch("/api/v1/calling/settings", patch); qc.invalidateQueries({ queryKey: ["calling-settings"] }); qc.invalidateQueries({ queryKey: ["calling-status"] }); toast.success("Saved"); }
    catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); }
  };
  const active = (members.data ?? []).filter((m) => m.status === "active");
  return (
    <div className="space-y-4 border-t border-border pt-4">
      <CallingHooks hooks={s.data.hooks} />
      <div className="space-y-4 border-t border-border pt-4">
        <Field label="When a client calls back, ring" hint="Whoever handles the lead is its owner in the CRM. Clients not in the CRM ring the fallback person.">
          <NativeSelect value={r.inbound} disabled={busy} onChange={(e) => save({ inbound: e.target.value as Routing["inbound"] })}>
            <option value="lead_owner">The person handling that lead, else the fallback person</option>
            <option value="fallback">Always the fallback person</option>
          </NativeSelect>
        </Field>
        <Field label="Fallback person" hint="Needs a mobile number on their profile.">
          <NativeSelect value={r.fallback_user_id ?? ""} disabled={busy} onChange={(e) => save({ fallback_user_id: e.target.value || null })}>
            <option value="">Workspace owner</option>
            {active.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({m.role.name})</option>)}
          </NativeSelect>
        </Field>
        <Row title="Ring the fallback person if nobody picks up" hint="Also sends an unanswered hand-over back to whoever handed it over."><Switch checked={r.ring_fallback_too} disabled={busy} onCheckedChange={(v) => save({ ring_fallback_too: v })} aria-label="Ring the fallback person if nobody picks up" /></Row>
        <Row title="New numbers become leads" hint="A caller who isn't in the CRM yet is added as a lead from “call”."><Switch checked={r.create_leads} disabled={busy} onCheckedChange={(v) => save({ create_leads: v })} aria-label="New numbers become leads" /></Row>
        <Row title="Record calls" hint="Recordings are linked on each call. Tell clients calls may be recorded."><Switch checked={r.record} disabled={busy} onCheckedChange={(v) => save({ record: v })} aria-label="Record calls" /></Row>
        <Row title="Tell the client who they're being connected to" hint="“Please hold, connecting you to Priya.”"><Switch checked={r.greeting} disabled={busy} onCheckedChange={(v) => save({ greeting: v })} aria-label="Greeting" /></Row>
        <Row title="Ring the client first on outgoing calls" hint={s.data.has_flow ? "The client is rung, hears a short hold message, then your phone rings. Lets outgoing calls be handed over too." : "Add the call flow app ID (reconnect) to turn this on. Without it, outgoing calls can't be handed over."}><Switch checked={r.client_first} disabled={busy || !s.data.has_flow} onCheckedChange={(v) => save({ client_first: v })} aria-label="Ring the client first on outgoing calls" /></Row>
        <Field label="Ring each phone for"><NativeSelect value={String(r.ring_seconds)} disabled={busy} onChange={(e) => save({ ring_seconds: Number(e.target.value) })}>{[15, 20, 30, 45, 60].map((n) => <option key={n} value={n}>{n} seconds</option>)}</NativeSelect></Field>
      </div>
    </div>
  );
}
