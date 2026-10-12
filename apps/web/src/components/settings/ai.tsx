"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ExternalLink, KeyRound, Sparkles, Zap } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Badge, Button, ConfirmDialog, ErrorState, Input, Skeleton, Switch, Textarea, cn, formatDate, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";
import { Divided, FieldRow, SettingsSection } from "./ui";

type Provider = { key: string; label: string; fast: string; smart: string; audio: boolean; key_hint: string; key_url?: string };
type AiSettingsData = {
  connected: boolean; source: "workspace" | "platform" | "basic"; provider: string | null; key_last4: string | null; fast_model: string; smart_model: string; status: string; last_error: string | null; connected_at: string | null;
  features: Record<string, boolean>; mask_pii: boolean; monthly_limit: number | null; user_limit: number | null; instructions: string; active_provider: string; active_model: string | null;
  providers: Provider[]; feature_list: { key: string; label: string; description: string }[]; usage: { actions: number; input_tokens: number; output_tokens: number; by_feature: Record<string, number>; by_user?: { user_id: string; name: string; actions: number }[] };
};
type Body = Partial<{ provider: string; api_key: string; fast_model: string; smart_model: string; features: Record<string, boolean>; mask_pii: boolean; monthly_limit: number | null; user_limit: number | null; instructions: string }>;

const KEY_URLS: Record<string, string> = { openai: "https://platform.openai.com/api-keys", anthropic: "https://console.anthropic.com/settings/keys", gemini: "https://aistudio.google.com/app/apikey", openrouter: "https://openrouter.ai/keys" };
const BASIC = "Without a key the assistant still works in basic mode: it reads your data, makes simple changes like 'remind me to call Priya tomorrow', captures leads from text and fills My day. Connect a key for full conversations, photos, voice notes and writing.";
const num = (v: string) => (v.trim() === "" ? null : Math.max(1, Math.round(Number(v))));
const fmt = (n: number) => n.toLocaleString("en-IN");

export function AiSettings() {
  const { can, has } = useAccess(); const qc = useQueryClient(); const toast = useToast();
  const allowed = can("settings.manage") && has("ai_assistant");
  const q = useQuery({ queryKey: ["ai-settings"], enabled: allowed, queryFn: () => api.get<AiSettingsData>("/api/v1/ai/settings") });
  const s = q.data;
  const [provider, setProvider] = React.useState("openai"); const [key, setKey] = React.useState(""); const [fast, setFast] = React.useState(""); const [smart, setSmart] = React.useState("");
  const [monthly, setMonthly] = React.useState(""); const [perUser, setPerUser] = React.useState(""); const [instr, setInstr] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null); const [keyErr, setKeyErr] = React.useState<string | null>(null); const [rm, setRm] = React.useState(false);
  const loaded = React.useRef(false);
  React.useEffect(() => {
    if (!s || loaded.current) return; loaded.current = true;
    setProvider(s.provider ?? "openai"); setFast(s.fast_model); setSmart(s.smart_model); setMonthly(s.monthly_limit?.toString() ?? ""); setPerUser(s.user_limit?.toString() ?? ""); setInstr(s.instructions ?? "");
  }, [s]);

  const apply = (r: AiSettingsData) => { qc.setQueryData(["ai-settings"], r); qc.invalidateQueries({ queryKey: ["ai-status"] }); };
  const save = async (tag: string, body: Body, done?: string) => {
    setBusy(tag);
    try { const r = await api.put<AiSettingsData>("/api/v1/ai/settings", body); apply(r); if (done) toast.success(done); return r; }
    catch (e) { if (tag === "key") setKeyErr((e as Error).message); else toast.error("Couldn't save", (e as Error).message); }
    finally { setBusy(null); }
  };
  const connect = async () => { setKeyErr(null); const r = await save("key", { provider, api_key: key.trim() }, "AI key connected"); if (r) { setKey(""); setFast(r.fast_model); setSmart(r.smart_model); } };
  const test = async () => {
    setBusy("test");
    try { const r = await api.post<{ ok: boolean; model: string }>("/api/v1/ai/settings/test", {}); toast.success("Connection works", r.model ? `Replied using ${r.model}.` : undefined); }
    catch (e) { toast.error("Connection failed", (e as Error).message); }
    finally { setBusy(null); q.refetch(); qc.invalidateQueries({ queryKey: ["ai-status"] }); }
  };

  if (!has("ai_assistant")) return <ErrorState kind="permission" title="The AI assistant isn't in your plan" description="Upgrade to use the assistant across leads, flats, visits and reports." action={can("billing.manage") ? <Button asChild><Link href="/app/billing">See plans</Link></Button> : undefined} />;
  if (!can("settings.manage")) return <ErrorState kind="permission" />;
  if (q.isError) return <ErrorState kind="unavailable" description={(q.error as Error).message} onRetry={() => q.refetch()} />;
  if (!s) return <div className="space-y-6"><Skeleton className="h-28" /><Skeleton className="h-80" /><Skeleton className="h-64" /></div>;

  const saved = s.providers.find((p) => p.key === s.provider); const pick = s.providers.find((p) => p.key === provider) ?? s.providers[0];
  const modelSpec = s.connected ? saved : pick; const switching = s.connected && provider !== s.provider;
  const featureLabel = (k: string) => s.feature_list.find((f) => f.key === k)?.label ?? k.replace(/_/g, " ");
  const byFeature = Object.entries(s.usage?.by_feature ?? {}).sort((a, b) => b[1] - a[1]); const maxF = Math.max(1, ...byFeature.map(([, v]) => v));
  const byUser = Array.isArray(s.usage?.by_user) ? s.usage.by_user.map((u) => [u.name, u.actions] as const) : [];
  const limitsDirty = monthly !== (s.monthly_limit?.toString() ?? "") || perUser !== (s.user_limit?.toString() ?? "") || instr !== (s.instructions ?? "");
  const modelsDirty = fast !== s.fast_model || smart !== s.smart_model;

  return (
    <div className="space-y-6">
      <div className={cn("flex items-start gap-3 rounded-xl border p-4", s.connected ? "border-success/30 bg-success-soft" : s.source === "platform" ? "border-primary/20 bg-primary-soft" : "border-border bg-surface-2")}>
        <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface", s.connected ? "text-success" : s.source === "platform" ? "text-primary" : "text-fg-muted")}>{s.connected ? <CheckCircle2 className="size-5" /> : s.source === "platform" ? <Sparkles className="size-5" /> : <Zap className="size-5" />}</span>
        <div className="min-w-0 flex-1 text-sm">
          {s.connected ? <><p className="font-semibold">Connected to {saved?.label ?? s.provider}</p><p className="mt-0.5 text-fg-muted">Key ending ••••{s.key_last4} · connected {formatDate(s.connected_at)}{s.active_model ? ` · chat uses ${s.active_model}` : ""}</p></>
            : s.source === "platform" ? <><p className="font-semibold">Using CRM Wala AI</p><p className="mt-0.5 text-fg-muted">The assistant runs on CRM Wala&apos;s own AI{s.active_model ? ` (${s.active_model})` : ""}. Connect your own key to use your provider and your own limits.</p></>
            : <><p className="font-semibold">Basic mode</p><p className="mt-0.5 text-fg-muted">{BASIC}</p></>}
          {s.last_error && <p role="alert" className="mt-2 flex items-start gap-1.5 text-[13px] text-danger"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{s.last_error}</p>}
        </div>
        <Badge tone={s.connected ? "success" : s.source === "platform" ? "primary" : "neutral"}>{s.connected ? "Your AI key" : s.source === "platform" ? "CRM Wala AI" : "Basic mode"}</Badge>
      </div>

      <SettingsSection title="Connect your AI key" description="Use your own OpenAI, Claude, Gemini or OpenRouter account. The key is stored encrypted and never shown again."
        actions={s.connected ? <div className="flex gap-2"><Button variant="secondary" size="sm" onClick={test} loading={busy === "test"}>Test connection</Button><Button variant="danger-soft" size="sm" onClick={() => setRm(true)}>Remove key</Button></div> : undefined}>
        <div className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">{s.providers.map((p) => <button key={p.key} type="button" onClick={() => { setProvider(p.key); setKeyErr(null); const same = p.key === s.provider; setFast(same ? s.fast_model : ""); setSmart(same ? s.smart_model : ""); }} aria-pressed={provider === p.key} className={cn("rounded-lg border p-3 text-left transition-colors", provider === p.key ? "border-primary bg-primary-soft/50 ring-1 ring-primary/30" : "border-border hover:border-border-strong")}>
            <p className="flex items-center gap-2 text-sm font-medium">{p.label}{s.connected && s.provider === p.key && <Badge tone="success">Connected</Badge>}</p><p className="mt-0.5 text-xs text-fg-muted">{p.key_hint}{p.audio ? " · understands voice notes" : ""}</p></button>)}</div>
          {switching && <p className="rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">Switching provider needs a new key. Your {saved?.label ?? "current"} key is replaced when you save.</p>}
          <div className="max-w-md space-y-2">
            <label className="text-sm font-medium" htmlFor="ai-key">{pick.label} API key</label>
            <Input id="ai-key" type="password" autoComplete="off" value={key} onChange={(e) => { setKey(e.target.value); setKeyErr(null); }} placeholder={s.connected && !switching ? `••••${s.key_last4} (paste a new key to replace it)` : pick.key_hint} />
            <a href={pick.key_url ?? KEY_URLS[pick.key]} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Get a {pick.label} key <ExternalLink className="size-3" /></a>
            {keyErr && <p role="alert" className="text-sm text-danger">{keyErr}</p>}
          </div>
          <div className="flex items-center gap-3"><Button onClick={connect} loading={busy === "key"} disabled={key.trim().length < 8}><KeyRound /> Test & save</Button><p className="text-xs text-fg-subtle">We send a tiny test message first, so a wrong key is never saved.</p></div>
        </div>
      </SettingsSection>

      <SettingsSection title="Models" description="Leave blank to use the recommended model." actions={<Button size="sm" onClick={() => save("models", { fast_model: fast.trim(), smart_model: smart.trim() }, "Models saved")} loading={busy === "models"} disabled={!s.connected || !modelsDirty}>Save</Button>}>
        <Divided>
          <FieldRow label="Fast model" hint="Quick jobs like capturing leads, search and import."><Input value={fast} onChange={(e) => setFast(e.target.value)} placeholder={modelSpec?.fast ?? ""} disabled={!s.connected} aria-label="Fast model" /></FieldRow>
          <FieldRow label="Smart model" hint="Chat, reports, insights and writing."><Input value={smart} onChange={(e) => setSmart(e.target.value)} placeholder={modelSpec?.smart ?? ""} disabled={!s.connected} aria-label="Smart model" /></FieldRow>
        </Divided>
        {!s.connected && <p className="mt-2 text-xs text-fg-subtle">Connect your own key to choose models.</p>}
      </SettingsSection>

      <SettingsSection title="Features" description="Turn parts of the assistant on or off for everyone in the workspace.">
        <Divided>{s.feature_list.map((f) => <div key={f.key} className="flex items-start justify-between gap-4 py-3"><div><p className="text-sm font-medium">{f.label}</p><p className="mt-0.5 text-xs text-fg-muted">{f.description}</p></div>
          <Switch checked={s.features[f.key] !== false} disabled={busy === `f:${f.key}`} onCheckedChange={(v) => save(`f:${f.key}`, { features: { [f.key]: v } }, `${f.label} ${v ? "turned on" : "turned off"}`)} aria-label={f.label} /></div>)}</Divided>
      </SettingsSection>

      <SettingsSection title="Privacy & limits" actions={<Button size="sm" onClick={() => save("limits", { monthly_limit: num(monthly), user_limit: num(perUser), instructions: instr }, "Saved")} loading={busy === "limits"} disabled={!limitsDirty}>Save</Button>}>
        <Divided>
          <FieldRow label="Hide contact details" hint="Phone numbers and emails are replaced before anything is sent to the AI provider."><label className="flex items-center gap-3 text-sm"><Switch checked={s.mask_pii} disabled={busy === "pii"} onCheckedChange={(v) => save("pii", { mask_pii: v }, v ? "Contact details hidden from the AI" : "Contact details no longer hidden")} aria-label="Hide phone numbers and emails from the AI provider" />Hide phone numbers and emails from the AI provider</label></FieldRow>
          <FieldRow label="Monthly limit" hint="AI actions for the whole workspace each month. Blank = no limit beyond your plan."><Input type="number" min={1} value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="No limit" aria-label="Monthly limit" /></FieldRow>
          <FieldRow label="Limit per person" hint="AI actions each person can use a month. Blank = no limit beyond your plan."><Input type="number" min={1} value={perUser} onChange={(e) => setPerUser(e.target.value)} placeholder="No limit" aria-label="Limit per person" /></FieldRow>
          <FieldRow label="Instructions" hint="Things the assistant should always keep in mind."><Textarea rows={4} maxLength={1000} value={instr} onChange={(e) => setInstr(e.target.value)} placeholder="e.g. We sell in Noida. Always reply in Hinglish. Sign messages as Team Skyline" aria-label="Instructions" /><p className="mt-1 text-right text-xs text-fg-subtle">{instr.length}/1000</p></FieldRow>
        </Divided>
      </SettingsSection>

      <SettingsSection title="Usage this month" description="Counted from the 1st of the month.">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-surface-2 p-3"><p className="text-xs text-fg-muted">AI actions</p><p className="tabular text-xl font-semibold">{fmt(s.usage?.actions ?? 0)}{s.monthly_limit ? <span className="text-sm font-normal text-fg-muted"> / {fmt(s.monthly_limit)}</span> : null}</p></div>
          <div className="rounded-lg bg-surface-2 p-3"><p className="text-xs text-fg-muted">Words sent (tokens)</p><p className="tabular text-xl font-semibold">{fmt(s.usage?.input_tokens ?? 0)}</p></div>
          <div className="rounded-lg bg-surface-2 p-3"><p className="text-xs text-fg-muted">Words received (tokens)</p><p className="tabular text-xl font-semibold">{fmt(s.usage?.output_tokens ?? 0)}</p></div>
        </div>
        {byFeature.length > 0 && <div className="mt-5"><p className="mb-2 text-sm font-medium">By feature</p><ul className="space-y-2">{byFeature.map(([k, v]) => <li key={k} className="grid grid-cols-[140px_1fr_48px] items-center gap-3 text-[13px] sm:grid-cols-[200px_1fr_56px]"><span className="truncate">{featureLabel(k)}</span><span className="h-2 overflow-hidden rounded-full bg-bg-subtle"><span className="block h-full rounded-full bg-primary" style={{ width: `${(v / maxF) * 100}%` }} /></span><span className="tabular text-right text-fg-muted">{fmt(v)}</span></li>)}</ul></div>}
        {byUser.length > 0 && <div className="mt-5"><p className="mb-2 text-sm font-medium">By person</p><ul className="divide-y divide-border">{byUser.map(([n, v]) => <li key={n} className="flex justify-between py-1.5 text-[13px]"><span>{n}</span><span className="tabular text-fg-muted">{fmt(Number(v))}</span></li>)}</ul></div>}
        {!s.usage?.actions && <p className="mt-3 text-xs text-fg-subtle">No AI actions yet this month.</p>}
      </SettingsSection>

      <ConfirmDialog open={rm} onOpenChange={setRm} title="Remove the AI key?" confirmLabel="Remove key" description="The assistant goes back to CRM Wala AI or basic mode until a new key is connected. Your feature switches and limits stay as they are."
        onConfirm={async () => { await api.delete("/api/v1/ai/settings/key"); await q.refetch(); qc.invalidateQueries({ queryKey: ["ai-status"] }); setFast(""); setSmart(""); toast.success("AI key removed"); }} />
    </div>
  );
}
