"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, Send } from "lucide-react";
import * as React from "react";
import { ApiError, Badge, Button, ConfirmDialog, Field, Input, NativeSelect, Skeleton, Switch, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { SettingsSection } from "./ui";

type Preset = { key: string; label: string; host: string; port: number; help: string };
type CompanyEmail = { status: string; last_error?: string | null; preset?: string; host?: string; port?: number; username?: string; from_address: string; from_name?: string; own_address: boolean; has_password?: boolean; presets?: Preset[] };

/** Owner sets up the firm's own email account once; everyone's CRM email then goes out through it. */
export function CompanyEmailSettings() {
  const { data: me } = useMe(); const qc = useQueryClient(); const toast = useToast(); const owner = me?.role?.key === "owner";
  const q = useQuery({ queryKey: ["company-email"], queryFn: () => api.get<CompanyEmail>("/api/v1/emails/company") });
  const [f, setF] = React.useState({ preset: "google", host: "", port: 587, username: "", password: "", from_address: "", from_name: "", own_address: false });
  const [editing, setEditing] = React.useState(false); const [busy, setBusy] = React.useState(false); const [testing, setTesting] = React.useState(false);
  const [err, setErr] = React.useState<Record<string, string> | null>(null); const [off, setOff] = React.useState(false);
  const d = q.data; const connected = d && d.status !== "not_connected";
  React.useEffect(() => {
    if (d && owner) setF({ preset: d.preset ?? "google", host: d.host ?? "", port: d.port ?? 587, username: d.username ?? "", password: "", from_address: d.from_address ?? "", from_name: d.from_name ?? "", own_address: d.own_address });
  }, [d, owner]);
  const preset = d?.presets?.find((p) => p.key === f.preset);
  const custom = f.preset === "other";
  const refresh = (v: CompanyEmail) => { qc.setQueryData(["company-email"], v); qc.invalidateQueries({ queryKey: ["email-sender"] }); };

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const v = await api.put<CompanyEmail>("/api/v1/emails/company", { ...f, host: custom ? f.host : "", port: custom ? Number(f.port) || 587 : preset?.port ?? 587 });
      refresh(v); setEditing(false); toast.success("Company email connected", "Everyone's emails now go out from this account.");
    } catch (e) { setErr(e instanceof ApiError && e.details ? e.details as Record<string, string> : { form: (e as Error).message }); } finally { setBusy(false); }
  };
  const test = async () => {
    setTesting(true);
    try { const r = await api.post<{ sent_to: string }>("/api/v1/emails/company/test"); toast.success("Test email sent", `Check ${r.sent_to}.`); }
    catch (e) { toast.error("Test email failed", (e as Error).message); } finally { setTesting(false); q.refetch(); }
  };

  if (q.isLoading) return <Skeleton className="h-40" />;
  const form = owner && (editing || !connected);
  return (
    <SettingsSection title="Company email" description="Connect your company's email account once. Every employee's emails, comparisons and society pages then go out from it, under their own name, and replies come back to them."
      actions={owner && connected && !editing && <div className="flex gap-2"><Button variant="secondary" size="sm" onClick={test} loading={testing}><Send /> Send test</Button><Button variant="secondary" size="sm" onClick={() => setEditing(true)}>Change</Button></div>}>
      {!form && (connected
        ? <div className="space-y-2 text-sm">
            <p className="flex flex-wrap items-center gap-2">{d!.status === "error" ? <Badge tone="danger" dot>Not sending</Badge> : <Badge tone="success" dot>Connected</Badge>}<span className="font-medium">{d!.from_address}</span></p>
            {d!.status === "error" && d!.last_error && <p className="text-[13px] text-danger">{d!.last_error}</p>}
            <p className="text-[13px] text-fg-muted">{d!.own_address ? "Employees whose address is on this domain send from their own address. Everyone else sends from this one." : "Emails show the employee's name, come from this address, and replies go to the employee."}</p>
            {owner && <Button variant="ghost" size="xs" className="text-danger" onClick={() => setOff(true)}>Disconnect</Button>}
          </div>
        : <p className="flex items-center gap-2 text-sm text-fg-muted"><Mail className="size-4" />Not set up yet. Ask the workspace owner to connect the company email.</p>)}
      {form && (
        <div className="max-w-lg space-y-4">
          <Field label="Email provider" hint={preset?.help}>
            <NativeSelect value={f.preset} onChange={(e) => setF({ ...f, preset: e.target.value })}>{d?.presets?.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</NativeSelect>
          </Field>
          <Field label="Company email address" hint="Emails go out from this address." error={err?.from_address}><Input type="email" value={f.from_address} onChange={(e) => setF({ ...f, from_address: e.target.value })} placeholder="sales@yourcompany.com" /></Field>
          {custom && <div className="grid gap-3 sm:grid-cols-[1fr_110px]">
            <Field label="SMTP server" error={err?.host}><Input value={f.host} onChange={(e) => setF({ ...f, host: e.target.value })} placeholder="smtp.yourcompany.com" /></Field>
            <Field label="Port"><Input inputMode="numeric" value={String(f.port)} onChange={(e) => setF({ ...f, port: Number(e.target.value.replace(/\D/g, "")) || 0 })} /></Field>
          </div>}
          <Field label="Login" hint="Leave blank if it's the same as the address above."><Input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} placeholder={f.from_address || "Usually the email address"} /></Field>
          <Field label={f.preset === "google" ? "App password" : "Password"} hint={d?.has_password ? "Leave blank to keep the saved password." : undefined} error={err?.password ?? err?.form}>
            <Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} placeholder={d?.has_password ? "••••••••" : ""} />
          </Field>
          <Field label="Company name in the sender (optional)" hint={`Shows as "${me?.user?.name ?? "Ravi"}${f.from_name ? ` | ${f.from_name}` : ""}".`}><Input value={f.from_name} onChange={(e) => setF({ ...f, from_name: e.target.value })} placeholder={me?.workspace?.name ?? ""} maxLength={80} /></Field>
          <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
            <div><p className="text-sm font-medium">Send from each employee&apos;s own address</p><p className="mt-0.5 text-xs text-fg-muted">For employees whose login email is on the same domain. Your email server must allow this login to send as them (for example Google Workspace with &quot;Send mail as&quot;, or an SMTP relay).</p></div>
            <Switch checked={f.own_address} onCheckedChange={(v) => setF({ ...f, own_address: v })} aria-label="Send from each employee's own address" />
          </div>
          <div className="flex gap-2"><Button onClick={save} loading={busy} disabled={!f.from_address.trim() || (!f.password && !d?.has_password) || (custom && !f.host.trim())}>{connected ? "Save" : "Connect"}</Button>{editing && <Button variant="secondary" onClick={() => { setEditing(false); setErr(null); }}>Cancel</Button>}</div>
          <p className="text-xs text-fg-subtle">We log in once to check the details, and store the password encrypted.</p>
        </div>
      )}
      <ConfirmDialog open={off} onOpenChange={setOff} title="Disconnect company email?" confirmLabel="Disconnect" description="Employees' emails won't go out from your company account any more."
        onConfirm={async () => { await api.delete("/api/v1/emails/company"); await q.refetch(); qc.invalidateQueries({ queryKey: ["email-sender"] }); toast.success("Company email disconnected"); }} />
    </SettingsSection>
  );
}
