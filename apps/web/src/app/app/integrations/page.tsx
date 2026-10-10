"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Clipboard, Plug, RefreshCw, Search, Webhook as WebhookIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { Badge, Button, Card, ConfirmDialog, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Field, Input, Skeleton, cn, timeAgo, useToast } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

type Integ = { provider: string; name: string; category: string; description: string; feature: string | null; status: "not_connected" | "connected" | "error" | "reconnect"; mode: "live" | "sandbox" | null; account_label: string | null; last_synced_at: string | null; last_error: string | null; config: { endpoints?: { url: string; events: string[] }[] }; live_capable: boolean };
type Resp = { categories: string[]; integrations: Integ[]; webhook_events: string[]; lead_form: { token: string; endpoint: string } };
const COLORS: Record<string, string> = { gmail: "#ea4335", outlook: "#0a64c8", slack: "#611f69", microsoft_teams: "#5b5fc7", whatsapp: "#25d366", zoom: "#2d8cff", google_calendar: "#4285f4", google_contacts: "#4285f4", google_sheets: "#0f9d58", stripe: "#635bff", razorpay: "#0c2451", mailchimp: "#f7b500", meta_lead_ads: "#1877f2", google_analytics: "#f9ab00", zapier: "#ff4a00", webhooks: "#475569" };
const STATUS = { connected: ["success", "Connected"], not_connected: ["neutral", "Not connected"], error: ["danger", "Error"], reconnect: ["warning", "Reconnect"] } as const;

function Copy({ text, label }: { text: string; label: string }) {
  const [ok, setOk] = React.useState(false);
  return <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2"><code className="min-w-0 flex-1 truncate text-xs">{text}</code><Button size="xs" variant="ghost" aria-label={`Copy ${label}`} onClick={() => { navigator.clipboard?.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}>{ok ? <Check /> : <Clipboard />}</Button></div>;
}

export default function IntegrationsPage() {
  const qc = useQueryClient(); const toast = useToast(); const { can, has } = useAccess(); const sp = useSearchParams();
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<Resp>("/api/v1/integrations") });
  const [cat, setCat] = React.useState("All"); const [search, setSearch] = React.useState(""); const [dlg, setDlg] = React.useState<Integ | null>(null); const [disc, setDisc] = React.useState<Integ | null>(null);
  const [url, setUrl] = React.useState(""); const [eps, setEps] = React.useState("");  const [secret, setSecret] = React.useState<string | null>(null); const [busy, setBusy] = React.useState(false); const [err, setErr] = React.useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["integrations"] });
  React.useEffect(() => { const c = sp.get("connect"); if (c && q.data) { const i = q.data.integrations.find((x) => x.provider === c); if (i) setDlg(i); } if (sp.get("connected")) toast.success("Connected"); if (sp.get("error")) toast.error("Couldn't connect", "Authorisation failed. Please try again."); }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const sync = useMutation({ mutationFn: (p: string) => api.post<{ imported: number }>(`/api/v1/integrations/${p}/sync`), onSuccess: (r) => { refresh(); qc.invalidateQueries({ queryKey: ["contacts"] }); toast.success("Sync complete", r.imported ? `${r.imported} contacts imported.` : "Everything is up to date."); }, onError: (e) => toast.error("Sync failed", (e as Error).message) });
  const connect = async (i: Integ) => {
    setBusy(true); setErr(null);
    try {
      const body = i.provider === "slack" ? { webhook_url: url } : i.provider === "webhooks" ? { endpoints: eps.split("\n").map((l) => l.trim()).filter(Boolean).map((u) => ({ url: u, events: [] })) } : {};
      const r = await api.post<Integ & { auth_url?: string; signing_secret?: string }>(`/api/v1/integrations/${i.provider}/connect`, body);
      if (r.auth_url) { window.location.href = r.auth_url; return; }
      if (r.signing_secret) { setSecret(r.signing_secret); } else { setDlg(null); toast.success(`${i.name} connected`, r.mode === "sandbox" ? "Running in sandbox mode — no data leaves your workspace." : undefined); }
      refresh();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  if (q.isError) return <PageContainer><ErrorState kind="unavailable" onRetry={() => q.refetch()} /></PageContainer>;
  const all = q.data?.integrations ?? []; const cats = ["All", ...(q.data?.categories ?? [])];
  const shown = all.filter((i) => (cat === "All" || i.category === cat) && (!search || (i.name + i.description).toLowerCase().includes(search.toLowerCase())));
  const connected = all.filter((i) => i.status !== "not_connected").length; const manage = can("integrations.manage");
  return (
    <PageContainer>
      <PageHeader title="Integrations" description={`${connected} connected · connect the tools your team already uses.`} />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="hide-scrollbar flex gap-1 overflow-x-auto">{cats.map((c) => <button key={c} onClick={() => setCat(c)} className={cn("shrink-0 rounded-full px-3.5 py-1.5 text-[13px] font-medium", cat === c ? "bg-fg text-bg" : "text-fg-muted hover:bg-surface-hover")}>{c}</button>)}</div>
        <div className="ml-auto w-full sm:w-64"><Input icon={<Search />} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search integrations…" aria-label="Search integrations" /></div>
      </div>
      {q.isLoading ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44" />)}</div> : !shown.length ? <EmptyState icon={<Plug />} title="No integrations match" description="Try a different search or category." /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((i) => { const [tone, lbl] = STATUS[i.status]; const locked = !!i.feature && !has(i.feature); return (
            <Card key={i.provider} hover className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-3"><span className="flex size-11 items-center justify-center rounded-xl text-lg font-bold text-white shadow-sm" style={{ background: COLORS[i.provider] ?? "#64748b" }}>{i.name[0]}</span><div className="flex flex-col items-end gap-1"><Badge tone={tone} dot>{lbl}</Badge>{i.mode === "sandbox" && i.status === "connected" && <Badge tone="warning">Sandbox</Badge>}</div></div>
              <h3 className="mt-4 font-semibold">{i.name}</h3><p className="mt-1 flex-1 text-[13px] text-fg-muted">{i.description}</p>
              {(i.status === "error" || i.status === "reconnect") && <p className="mt-3 flex gap-2 rounded-lg bg-warning-soft p-2.5 text-xs text-warning"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{i.last_error}</p>}
              {i.status === "connected" && <p className="mt-3 truncate text-xs text-fg-subtle">{i.account_label}{i.last_synced_at && ` · synced ${timeAgo(i.last_synced_at)}`}</p>}
              <div className="mt-4 flex gap-2">
                {locked ? <Button variant="secondary" size="sm" className="flex-1" disabled>Upgrade to use</Button>
                  : i.status === "not_connected" ? <Button size="sm" className="flex-1" disabled={!manage} onClick={() => { setDlg(i); setUrl(""); setEps(""); setSecret(null); setErr(null); }}>Connect</Button>
                  : i.status === "connected" ? <>{["google_contacts", "gmail", "google_calendar", "google_sheets"].includes(i.provider) && <Button size="sm" variant="secondary" disabled={!manage} loading={sync.isPending && sync.variables === i.provider} onClick={() => sync.mutate(i.provider)}><RefreshCw /> Sync</Button>}<Button size="sm" variant="secondary" className="flex-1" disabled={!manage} onClick={() => { setDlg(i); setSecret(null); setErr(null); }}>Manage</Button></>
                  : <Button size="sm" className="flex-1" disabled={!manage} onClick={() => connect(i)} loading={busy}>Reconnect</Button>}
              </div>
            </Card>); })}
        </div>)}
      {q.data && <Card className="mt-8 p-6"><div className="flex items-start gap-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary"><WebhookIcon className="size-5" /></span><div className="min-w-0 flex-1"><h3 className="font-semibold">Lead capture form endpoint</h3><p className="mt-1 text-[13px] text-fg-muted">POST JSON from your website form or Zapier to create leads instantly. Include <code className="rounded bg-bg-subtle px-1">first_name</code>, <code className="rounded bg-bg-subtle px-1">email</code>, <code className="rounded bg-bg-subtle px-1">company</code>, <code className="rounded bg-bg-subtle px-1">message</code>.</p>
        <div className="mt-3 space-y-2"><Copy label="form endpoint" text={q.data.lead_form.endpoint} /><Copy label="inbound email endpoint" text={q.data.lead_form.endpoint.replace("/public/forms/", "/inbound/email/")} /></div></div></div></Card>}

      <Dialog open={!!dlg} onOpenChange={(o) => { if (!o) { setDlg(null); setSecret(null); } }}>
        {dlg && <DialogContent size="md" title={`${dlg.status === "connected" ? "Manage" : "Connect"} ${dlg.name}`} description={dlg.description}>
          <div className="space-y-4">
            {dlg.status === "connected" ? <>
              <p className="text-sm text-fg-muted">Connected as <strong className="text-fg">{dlg.account_label}</strong>{dlg.mode === "sandbox" && " (sandbox)"}.</p>
              {dlg.provider === "webhooks" && dlg.config.endpoints && <ul className="space-y-1 text-xs text-fg-muted">{dlg.config.endpoints.map((e) => <li key={e.url} className="truncate">• {e.url}</li>)}</ul>}
              {dlg.provider === "webhooks" && <Button variant="secondary" size="sm" onClick={async () => { await api.post("/api/v1/integrations/webhooks/test"); toast.success("Test event sent"); refresh(); }}>Send test event</Button>}
              {process.env.NODE_ENV !== "production" && <div className="flex gap-2 border-t border-border pt-3"><span className="mr-auto self-center text-xs text-fg-subtle">Demo helpers</span><Button size="xs" variant="ghost" onClick={async () => { await api.post(`/api/v1/integrations/${dlg.provider}/simulate-error`, { state: "error" }); refresh(); setDlg(null); }}>Simulate error</Button><Button size="xs" variant="ghost" onClick={async () => { await api.post(`/api/v1/integrations/${dlg.provider}/simulate-error`, { state: "reconnect" }); refresh(); setDlg(null); }}>Simulate reconnect</Button></div>}
              <DialogFooter><Button variant="danger-soft" onClick={() => { setDisc(dlg); setDlg(null); }}>Disconnect</Button><Button variant="secondary" onClick={() => setDlg(null)}>Done</Button></DialogFooter>
            </> : secret ? <>
              <p className="text-sm">Connected. Copy your <strong>signing secret</strong> now — it's only shown once. Verify the <code className="rounded bg-bg-subtle px-1">X-CRM-Signature</code> header (HMAC-SHA256 of the body).</p><Copy label="signing secret" text={secret} /><DialogFooter><Button onClick={() => { setDlg(null); setSecret(null); }}>I've saved it</Button></DialogFooter>
            </> : <>
              {dlg.provider === "slack" && <Field label="Slack incoming webhook URL" error={err ?? undefined} hint="Create one in Slack → Apps → Incoming Webhooks."><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.slack.com/services/…" /></Field>}
              {dlg.provider === "webhooks" && <Field label="Endpoint URLs (https, one per line)" error={err ?? undefined} hint={`Events: ${q.data?.webhook_events.join(", ")}`}><textarea className="min-h-24 w-full rounded-md border border-border bg-surface p-3 text-sm focus:border-primary focus:outline-none focus:ring-4 focus:ring-[var(--ring)]" value={eps} onChange={(e) => setEps(e.target.value)} placeholder="https://example.com/crm-webhook" /></Field>}
              {!["slack", "webhooks"].includes(dlg.provider) && <div className="rounded-lg bg-bg-subtle p-4 text-sm text-fg-muted">{dlg.live_capable ? <>You'll be redirected to authorise {dlg.name}.</> : <>This workspace will connect in <strong className="text-fg">sandbox mode</strong> because provider credentials aren't configured on this server. The full flow works, but nothing is sent to {dlg.name}.</>}</div>}
              {err && !["slack", "webhooks"].includes(dlg.provider) && <p role="alert" className="text-sm text-danger">{err}</p>}
              <DialogFooter><Button variant="secondary" onClick={() => setDlg(null)}>Cancel</Button><Button onClick={() => connect(dlg)} loading={busy} disabled={(dlg.provider === "slack" && !url) || (dlg.provider === "webhooks" && !eps.trim())}>Connect {dlg.name}</Button></DialogFooter>
            </>}
          </div></DialogContent>}
      </Dialog>
      <ConfirmDialog open={!!disc} onOpenChange={(o) => !o && setDisc(null)} title={`Disconnect ${disc?.name}?`} description="Syncing stops immediately. Existing CRM data isn't deleted." confirmLabel="Disconnect" onConfirm={async () => { await api.post(`/api/v1/integrations/${disc!.provider}/disconnect`); refresh(); toast.success("Disconnected"); }} />
    </PageContainer>
  );
}
