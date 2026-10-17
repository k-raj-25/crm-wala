"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clipboard } from "lucide-react";
import * as React from "react";
import { Button, Field, Input, NativeSelect, Skeleton, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useWaTemplates } from "./whatsapp";

export type WaCreds = { phone_number_id: string; waba_id: string; access_token: string; app_secret: string };
export type WaWebhook = { url: string; verify_token: string };
type Settings = { account_label: string; webhook: WaWebhook; media_template: { name: string; language: string } | null; recap_template: { name: string; language: string } | null };

function CopyRow({ label, text }: { label: string; text: string }) {
  const [ok, setOk] = React.useState(false);
  return (
    <Field label={label}>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2"><code className="min-w-0 flex-1 truncate text-xs">{text}</code><Button size="xs" variant="ghost" aria-label={`Copy ${label}`} onClick={() => { navigator.clipboard?.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}>{ok ? <Check /> : <Clipboard />}</Button></div>
    </Field>
  );
}

/** The four details each organisation copies from its own Meta app. On a reconnect, blank fields keep the saved values. */
export function WhatsAppConnectFields({ value, onChange, reconnect }: { value: WaCreds; onChange: (v: WaCreds) => void; reconnect?: boolean }) {
  const set = (k: keyof WaCreds) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-muted">Copy these from your app in <b className="text-fg">Meta for Developers → WhatsApp → API Setup</b>. Use a permanent System User token with the <code className="rounded bg-bg-subtle px-1">whatsapp_business_messaging</code> and <code className="rounded bg-bg-subtle px-1">whatsapp_business_management</code> permissions.{reconnect && " Leave a field empty to keep the saved value."}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Phone number ID"><Input value={value.phone_number_id} onChange={set("phone_number_id")} inputMode="numeric" autoComplete="off" /></Field>
        <Field label="WhatsApp Business Account ID"><Input value={value.waba_id} onChange={set("waba_id")} inputMode="numeric" autoComplete="off" /></Field>
      </div>
      <Field label="Access token"><Input type="password" value={value.access_token} onChange={set("access_token")} autoComplete="off" /></Field>
      <Field label="App secret" hint="Used to check that incoming messages really come from Meta."><Input type="password" value={value.app_secret} onChange={set("app_secret")} autoComplete="off" /></Field>
    </div>
  );
}

export function WhatsAppWebhook({ hook, intro }: { hook: WaWebhook; intro?: boolean }) {
  return (
    <div className="space-y-3">
      {intro && <p className="text-sm">Connected. To get client replies on the timeline, open <b>WhatsApp → Configuration</b> in your Meta app, paste these as the webhook, and subscribe to the <code className="rounded bg-bg-subtle px-1">messages</code> field.</p>}
      <CopyRow label="Callback URL" text={hook.url} />
      <CopyRow label="Verify token" text={hook.verify_token} />
    </div>
  );
}

/** Manage view: webhook details, and the approved template used to send brochures to clients outside the 24-hour window. */
export function WhatsAppManage() {
  const qc = useQueryClient(); const toast = useToast();
  const s = useQuery({ queryKey: ["wa-settings"], queryFn: () => api.get<Settings>("/api/v1/whatsapp/settings") });
  const templates = useWaTemplates();
  const [busy, setBusy] = React.useState(false);
  if (s.isLoading) return <Skeleton className="h-32 w-full" />;
  if (!s.data) return null;
  const media = (templates.data ?? []).filter((t) => (t.header === "DOCUMENT" || t.header === "IMAGE") && t.supported && t.body_params <= 2);
  const recapTemplates = (templates.data ?? []).filter((t) => (!t.header || t.header === "TEXT") && t.supported && t.body_params >= 1 && t.body_params <= 2);
  const key = (t: { name: string; language: string } | null) => (t ? `${t.name}|${t.language}` : "");
  const current = key(s.data.media_template);
  const save = async (v: string, field: "media_template" | "recap_template" = "media_template") => {
    setBusy(true);
    try { await api.patch("/api/v1/whatsapp/settings", { [field]: v || null }); qc.invalidateQueries({ queryKey: ["wa-settings"] }); toast.success("Saved"); }
    catch (e) { toast.error("Couldn't save", (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4 border-t border-border pt-4">
      <WhatsAppWebhook hook={s.data.webhook} />
      <Field label="Brochure template" hint="WhatsApp only allows templates when a client hasn't written to you in 24 hours. Pick an approved template with a document header and brochures go out with it automatically. Its placeholders are filled with the client's first name, then the flat or project.">
        <NativeSelect value={current} disabled={busy || templates.isLoading} onChange={(e) => save(e.target.value)}>
          <option value="">None: only send files after the client replies</option>
          {media.map((t) => <option key={`${t.name}|${t.language}`} value={`${t.name}|${t.language}`}>{t.name.replace(/_/g, " ")} ({t.language})</option>)}
        </NativeSelect>
      </Field>
      <Field label="Visit recap template" hint="Used to send the visit recap link when the buyer hasn't written to you in 24 hours. Pick an approved text template with one or two placeholders: the client's first name, then the link. Without one, the recap opens in your own WhatsApp instead.">
        <NativeSelect value={key(s.data.recap_template)} disabled={busy || templates.isLoading} onChange={(e) => save(e.target.value, "recap_template")}>
          <option value="">None: open the recap in my WhatsApp</option>
          {recapTemplates.map((t) => <option key={`${t.name}|${t.language}`} value={`${t.name}|${t.language}`}>{t.name.replace(/_/g, " ")} ({t.language})</option>)}
        </NativeSelect>
      </Field>
    </div>
  );
}
