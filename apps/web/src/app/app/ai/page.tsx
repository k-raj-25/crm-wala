"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUp, Brain, History, MessageSquare, Plus, Sparkles, Trash2, TrendingDown, Wand2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Progress, Segmented, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, cn, formatMoneyCompact, useToast } from "@crm/ui";
import { Markdown } from "@/components/markdown";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { api } from "@/lib/api";
import { useAccess, useMe } from "@/lib/queries";

type Msg = { role: "user" | "assistant"; content: string; sources?: { label: string; url: string; type: string }[] };
const SUGGESTIONS = ["What should I focus on today?", "Which deals are most likely to close this month?", "Which leads haven't been contacted in 7 days?", "Show me my highest-value opportunities.", "Which salesperson has the highest conversion rate?", "Why is my pipeline declining?"];

function Chat() {
  const qc = useQueryClient(); const toast = useToast(); const { me } = useAccess();
  const [id, setId] = React.useState<string | null>(null); const [msgs, setMsgs] = React.useState<Msg[]>([]); const [text, setText] = React.useState(""); const [busy, setBusy] = React.useState(false);
  const end = React.useRef<HTMLDivElement>(null);
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: () => api.get<{ used: number; limit: number | null }>("/api/v1/ai/usage") });
  const convs = useQuery({ queryKey: ["ai-convs"], queryFn: () => api.get<{ id: string; title: string }[]>("/api/v1/ai/conversations") });
  React.useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);
  const open = async (cid: string) => { const c = await api.get<{ messages: Msg[] }>(`/api/v1/ai/conversations/${cid}`); setId(cid); setMsgs(c.messages); };
  const send = async (m: string) => {
    if (!m.trim() || busy) return; setText(""); setBusy(true); setMsgs((p) => [...p, { role: "user", content: m }]);
    try { const r = await api.post<{ conversation_id: string; answer: string; sources: Msg["sources"] }>("/api/v1/ai/chat", { message: m, conversation_id: id }); setId(r.conversation_id); setMsgs((p) => [...p, { role: "assistant", content: r.answer, sources: r.sources }]); qc.invalidateQueries({ queryKey: ["ai-usage"] }); qc.invalidateQueries({ queryKey: ["ai-convs"] }); }
    catch (e) { setMsgs((p) => p.slice(0, -1)); setText(m); toast.error("The assistant couldn't answer", (e as Error).message); } finally { setBusy(false); }
  };
  const u = usage.data; const pct = u?.limit ? (u.used / u.limit) * 100 : 0;
  return (
    <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-4">
        <Button className="w-full" variant="secondary" onClick={() => { setId(null); setMsgs([]); }}><Plus /> New chat</Button>
        <Card className="p-4"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-subtle">AI usage this month</p>{u ? (u.limit ? <><p className="tabular text-xl font-semibold">{u.used}<span className="text-sm font-normal text-fg-muted"> / {u.limit}</span></p><Progress value={u.used} max={u.limit} tone={pct > 90 ? "danger" : pct > 70 ? "warning" : "primary"} className="mt-2" label="AI usage" />{pct > 80 && <Link href="/app/billing" className="mt-2 block text-xs font-medium text-primary hover:underline">Running low — upgrade →</Link>}</> : <p className="text-sm text-fg-muted"><span className="tabular text-xl font-semibold text-fg">{u.used}</span> actions · fair use</p>) : <Skeleton className="h-10" />}</Card>
        <div className="hidden lg:block"><p className="mb-2 flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle"><History className="size-3.5" /> History</p>
          <ul className="space-y-0.5">{convs.data?.map((c) => <li key={c.id} className="group flex items-center"><button onClick={() => open(c.id)} className={cn("flex-1 truncate rounded-lg px-3 py-2 text-left text-[13px]", id === c.id ? "bg-primary-soft font-medium text-primary" : "text-fg-muted hover:bg-surface-hover")}>{c.title}</button><button aria-label="Delete conversation" onClick={async () => { await api.delete(`/api/v1/ai/conversations/${c.id}`); qc.invalidateQueries({ queryKey: ["ai-convs"] }); if (id === c.id) { setId(null); setMsgs([]); } }} className="rounded p-1 text-fg-subtle opacity-0 hover:text-danger group-hover:opacity-100"><Trash2 className="size-3.5" /></button></li>)}{convs.data?.length === 0 && <li className="px-3 text-xs text-fg-subtle">No conversations yet</li>}</ul></div>
      </aside>
      <Card className="flex min-h-[560px] flex-col overflow-hidden" style={{ height: "calc(100dvh - 300px)" }}>
        <div className="flex-1 overflow-y-auto p-5 sm:p-8" aria-live="polite">
          {msgs.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
              <span className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary"><Sparkles className="size-7" /></span>
              <h2 className="text-2xl font-semibold tracking-tight">Hi {me?.user.name.split(" ")[0]}, what can I help with?</h2><p className="mt-2 text-fg-muted">I answer from your own CRM data — only what you have permission to see.</p>
              <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-border bg-surface p-3.5 text-left text-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary-soft/40 hover:shadow-sm">{s}</button>)}</div>
            </div>
          ) : (
            <ul className="mx-auto max-w-3xl space-y-6">
              {msgs.map((m, i) => m.role === "user" ? <li key={i} className="flex justify-end"><p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-fg">{m.content}</p></li> : (
                <li key={i} className="flex gap-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><Sparkles className="size-4" /></span>
                  <div className="min-w-0 flex-1"><div className="rounded-2xl rounded-tl-md border border-border bg-surface px-5 py-4"><Markdown>{m.content}</Markdown></div>
                    {!!m.sources?.length && <div className="mt-2 flex flex-wrap gap-1.5">{m.sources.map((s, k) => <Link key={k} href={s.url} className="rounded-full border border-border px-2.5 py-0.5 text-xs text-fg-muted hover:border-primary/40 hover:text-primary">{s.label}</Link>)}</div>}</div></li>))}
              {busy && <li className="flex gap-3"><span className="flex size-8 items-center justify-center rounded-full bg-primary-soft text-primary"><Sparkles className="size-4" /></span><div className="flex items-center gap-1 rounded-2xl border border-border px-5 py-4" aria-label="Thinking">{[0, 1, 2].map((d) => <span key={d} className="size-2 animate-bounce rounded-full bg-fg-subtle" style={{ animationDelay: `${d * 120}ms` }} />)}</div></li>}
              <div ref={end} />
            </ul>)}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="border-t border-border bg-surface-2 p-3 sm:p-4"><div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-border bg-surface p-2 shadow-xs focus-within:border-primary focus-within:ring-4 focus-within:ring-[var(--ring)]">
          <textarea value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} rows={1} placeholder="Ask about your deals, leads, tasks, team…" aria-label="Message" className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-fg-subtle" />
          <Button type="submit" size="icon" disabled={!text.trim() || busy} aria-label="Send"><ArrowUp /></Button></div></form>
      </Card>
    </div>
  );
}

type Insight = { kind: string; title: string; reason: string; url: string; cta: string };
function Insights() {
  const { has } = useAccess();
  const nba = useQuery({ queryKey: ["nba"], enabled: has("ai_insights"), queryFn: () => api.get<Insight[]>("/api/v1/ai/next-best-actions") });
  const churn = useQuery({ queryKey: ["churn"], enabled: has("ai_insights"), queryFn: () => api.get<{ company_id: string; name: string; revenue: number; days_inactive: number; risk: number; reason: string; url: string }[]>("/api/v1/ai/churn-risk") });
  const clean = useQuery({ queryKey: ["cleanup"], enabled: has("ai_insights"), queryFn: () => api.get<{ kind: string; count: number; title: string; detail: string; url: string }[]>("/api/v1/ai/data-cleanup") });
  const diag = useQuery({ queryKey: ["diag"], enabled: has("ai_insights"), queryFn: () => api.get<{ direction: string; days: number; findings: { severity: string; title: string; detail: string }[] }>("/api/v1/ai/pipeline-diagnosis") });
  if (!has("ai_insights")) return <ErrorState kind="permission" title="AI insights are on Growth and above" description="Next-best-actions, churn-risk detection, pipeline diagnosis and data cleanup suggestions." action={<Button asChild><Link href="/app/billing">Compare plans</Link></Button>} />;
  const sev = { high: "danger", medium: "warning", low: "success" } as const;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader title={<span className="flex items-center gap-2"><Wand2 className="size-4 text-primary" /> Next best actions</span>} description="What to do next, in priority order" /><CardBody className="pt-3">{nba.isLoading ? <Skeleton className="h-40" /> : !nba.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">Nothing urgent. 🎉</p> : <ul className="space-y-2">{nba.data.map((a, i) => <li key={i}><Link href={a.url} className="flex items-center gap-3 rounded-lg border border-border p-3 hover:border-primary/40 hover:bg-primary-soft/40"><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{a.title}</span><span className="block text-xs text-fg-muted">{a.reason}</span></span><span className="text-xs font-medium text-primary">{a.cta} →</span></Link></li>)}</ul>}</CardBody></Card>
      <Card><CardHeader title={<span className="flex items-center gap-2"><TrendingDown className="size-4 text-primary" /> Pipeline diagnosis</span>} description={diag.data ? `Last ${diag.data.days} days vs the period before — looking ${diag.data.direction}` : undefined} /><CardBody className="pt-3">{diag.isLoading ? <Skeleton className="h-40" /> : <ul className="space-y-3">{diag.data?.findings.map((f, i) => <li key={i} className="flex gap-3"><Badge tone={sev[f.severity as keyof typeof sev] ?? "neutral"}>{f.severity}</Badge><div><p className="text-sm font-medium">{f.title}</p><p className="text-[13px] text-fg-muted">{f.detail}</p></div></li>)}</ul>}</CardBody></Card>
      <Card><CardHeader title={<span className="flex items-center gap-2"><AlertTriangle className="size-4 text-warning" /> Churn risk</span>} description="Customers going quiet" /><CardBody className="pt-3">{churn.isLoading ? <Skeleton className="h-32" /> : !churn.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">No customers at risk right now.</p> : <ul className="divide-y divide-border">{churn.data.map((c) => <li key={c.company_id}><Link href={c.url} className="flex items-center gap-3 py-3 hover:text-primary"><Avatar name={c.name} size={32} square /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{c.name}</span><span className="block text-xs text-fg-muted">{c.reason}</span></span><span className="text-right"><span className="tabular block text-sm font-semibold">{formatMoneyCompact(c.revenue)}</span><Badge tone={c.risk > 70 ? "danger" : "warning"}>{c.risk}% risk</Badge></span></Link></li>)}</ul>}</CardBody></Card>
      <Card><CardHeader title={<span className="flex items-center gap-2"><Brain className="size-4 text-primary" /> Data cleanup</span>} description="Keep your CRM tidy" /><CardBody className="pt-3">{clean.isLoading ? <Skeleton className="h-32" /> : !clean.data?.length ? <p className="py-6 text-center text-sm text-fg-muted">Your data looks clean. ✨</p> : <ul className="divide-y divide-border">{clean.data.map((c) => <li key={c.kind}><Link href={c.url} className="flex items-center justify-between gap-3 py-3 hover:text-primary"><span><span className="block text-sm font-medium">{c.title}</span><span className="block text-xs text-fg-muted">{c.detail}</span></span><Badge tone="warning">{c.count}</Badge></Link></li>)}</ul>}</CardBody></Card>
    </div>
  );
}

export default function AIPage() {
  const { has, can } = useAccess(); const [tab, setTab] = React.useState("chat");
  if (!has("ai_assistant") || !can("ai.use")) return <PageContainer><PageHeader title="AI Assistant" /><ErrorState kind="permission" title={!has("ai_assistant") ? "The AI assistant isn't in your plan" : "You don't have access to the AI assistant"} description={!has("ai_assistant") ? "Upgrade to ask questions about your pipeline, draft emails and get next-best-actions." : "Ask a workspace admin to enable it for your role."} action={!has("ai_assistant") ? <Button asChild><Link href="/app/billing">See plans</Link></Button> : undefined} /></PageContainer>;
  return (
    <PageContainer wide>
      <PageHeader title="AI Assistant" description="Ask questions in plain English. Answers come from your workspace data only." />
      <Tabs value={tab} onValueChange={setTab}><TabsList className="mb-6"><TabsTrigger value="chat"><MessageSquare className="size-4" /> Ask</TabsTrigger><TabsTrigger value="insights"><Sparkles className="size-4" /> Insights</TabsTrigger></TabsList>
        <TabsContent value="chat"><Chat /></TabsContent><TabsContent value="insights"><Insights /></TabsContent></Tabs>
    </PageContainer>
  );
}
export { Segmented, EmptyState };
