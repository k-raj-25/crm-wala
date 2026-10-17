"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, MessageCircle, Unlink } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Badge, Button, Field, NativeSelect, Skeleton, Switch, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { Divided, FieldRow, SettingsSection } from "../settings/ui";
import { useWaTemplates } from "./whatsapp";

type Me = {
  available: boolean; reason: string | null; company_number: string | null; profile_phone: string | null; linked: boolean; linked_at: string | null;
  morning_plan: boolean; new_leads: boolean; plan_hour: number; timezone: string; alert_template: boolean;
  link: { code: string; expires_at: string; message: string; wa_url: string | null } | null;
};

/** Notifications → WhatsApp: link your own number, then update the CRM by WhatsApp and get your plan and new leads there. */
export function WhatsAppForMe() {
  const qc = useQueryClient(); const toast = useToast();
  const q = useQuery({ queryKey: ["wa-me"], queryFn: () => api.get<Me>("/api/v1/whatsapp/me"), refetchInterval: (s) => (s.state.data?.link ? 4000 : false) });
  const [busy, setBusy] = React.useState(false);
  const run = async (fn: () => Promise<Me>) => {
    setBusy(true);
    try { qc.setQueryData(["wa-me"], await fn()); } catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); }
  };
  const d = q.data;
  return (
    <SettingsSection title="WhatsApp" description="Update the CRM without opening the app: send a text or voice note to your company's WhatsApp number and confirm the card that comes back."
      actions={d?.linked ? <Button variant="ghost" onClick={() => run(async () => { await api.delete("/api/v1/whatsapp/me"); return api.get<Me>("/api/v1/whatsapp/me"); })} loading={busy}><Unlink /> Unlink</Button> : undefined}>
      {q.isLoading || !d ? <Skeleton className="h-24" /> : !d.available ? <p className="text-sm text-fg-muted">{d.reason}</p> : (
        <div className="space-y-4">
          {d.linked ? (
            <p className="flex flex-wrap items-center gap-2 text-sm"><Badge tone="success" dot>Linked</Badge><span className="text-fg-muted">Messages from {d.profile_phone} to {d.company_number ?? "your company's number"} update the CRM as you. Send <b className="text-fg">help</b> there for examples.</span></p>
          ) : d.link ? (
            <div className="space-y-2 rounded-lg border border-border bg-bg-subtle p-3 text-sm">
              <p>From <b>{d.profile_phone}</b>, send this message to {d.company_number ? <b>{d.company_number}</b> : "your company's WhatsApp number"}:</p>
              <p className="select-all font-mono text-lg tracking-widest">{d.link.message}</p>
              {d.link.wa_url && <Button size="sm" asChild><a href={d.link.wa_url} target="_blank" rel="noreferrer"><MessageCircle /> Open WhatsApp <ExternalLink /></a></Button>}
              <p className="text-xs text-fg-muted">The code works for 30 minutes. This page updates once it arrives.</p>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              {d.profile_phone
                ? <><span className="text-fg-muted">Your number: <b className="text-fg">{d.profile_phone}</b>. Only messages from the number on your profile count as yours.</span><Button onClick={() => run(() => api.post<Me>("/api/v1/whatsapp/me/link"))} loading={busy}><MessageCircle /> Link my WhatsApp</Button></>
                : <span className="text-fg-muted">Add your mobile number in <Link className="text-accent underline" href="/app/settings/profile">Profile</Link> first.</span>}
            </div>
          )}
          <Divided>
            <FieldRow label="Morning plan" hint={`Today's visits, follow-ups and new enquiries at ${d.plan_hour} AM (${d.timezone.replace("_", " ")}).`}>
              <Switch checked={d.morning_plan} disabled={busy} onCheckedChange={(v) => run(() => api.patch<Me>("/api/v1/whatsapp/me", { morning_plan: v }))} aria-label="Morning plan on WhatsApp" />
            </FieldRow>
            <FieldRow label="New lead alerts" hint="A message for each new lead you're given.">
              <Switch checked={d.new_leads} disabled={busy} onCheckedChange={(v) => run(() => api.patch<Me>("/api/v1/whatsapp/me", { new_leads: v }))} aria-label="New lead alerts on WhatsApp" />
            </FieldRow>
          </Divided>
          {(d.morning_plan || d.new_leads) && !d.alert_template && <p className="text-xs text-fg-muted">WhatsApp only lets us message you first within 24 hours of your last message to us. Until an admin picks a team alert template, plans and alerts arrive only on days you've messaged us.</p>}
        </div>
      )}
    </SettingsSection>
  );
}

/** Admin: the approved template that carries morning plans and alerts when a rep hasn't messaged in 24 hours. */
export function TeamAlertTemplate() {
  const qc = useQueryClient(); const toast = useToast(); const { can } = useAccess();
  const s = useQuery({ queryKey: ["wa-team"], enabled: can("integrations.manage"), queryFn: () => api.get<{ team_template: { name: string; language: string } | null }>("/api/v1/whatsapp/team-settings") });
  const templates = useWaTemplates();
  const [busy, setBusy] = React.useState(false);
  if (!s.data) return null;
  const usable = (templates.data ?? []).filter((t) => t.supported && t.body_params === 1 && t.header !== "DOCUMENT" && t.header !== "IMAGE");
  const current = s.data.team_template ? `${s.data.team_template.name}|${s.data.team_template.language}` : "";
  const save = async (v: string) => {
    setBusy(true);
    try { await api.patch("/api/v1/whatsapp/team-settings", { team_template: v || null }); qc.invalidateQueries({ queryKey: ["wa-team"] }); toast.success("Saved"); }
    catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Field label="Team alert template" hint="Reps can link their own number and get their morning plan and new lead alerts on WhatsApp. When a rep hasn't messaged you in 24 hours, WhatsApp needs an approved template: pick a utility template with one placeholder, such as “CRM Wala: {{1}}”.">
      <NativeSelect value={current} disabled={busy || templates.isLoading} onChange={(e) => save(e.target.value)}>
        <option value="">None: only message reps who wrote in the last 24 hours</option>
        {usable.map((t) => <option key={`${t.name}|${t.language}`} value={`${t.name}|${t.language}`}>{t.name.replace(/_/g, " ")} ({t.language})</option>)}
      </NativeSelect>
    </Field>
  );
}
