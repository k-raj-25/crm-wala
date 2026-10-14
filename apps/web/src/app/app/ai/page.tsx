"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { History, MessageSquare, Plus, Sparkles, Sun, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";
import { Button, Card, ErrorState, Progress, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, cn } from "@crm/ui";
import { ModeBadge } from "@/components/ai/ai-dock";
import { Composer, Messages, pageContext, useAiChat } from "@/components/ai/chat";
import { Insights } from "@/components/ai/insights";
import { MyDay } from "@/components/ai/my-day";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { useAiStatus } from "@/lib/ai";
import { api } from "@/lib/api";
import { useAccess } from "@/lib/queries";

const SUGGESTIONS = ["Move Priya Sharma to Interested and remind me Friday 11am", "Which source brought the most site visits this month?", "Assign all new 99acres leads from today to Rohan", "Show 3BHK buyers in Sector 62 under 1.5 Cr", "Hold flat A-1204 for Mr Gupta for 2 days", "How do I add a tower?"];

function BasicNote() {
  const s = useAiStatus().data;
  if (s?.mode !== "basic") return null;
  return <p className="mb-4 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning">Basic mode: {s.can_manage ? <Link href="/app/settings/ai" className="font-semibold underline">connect your AI key in Settings → AI assistant</Link> : "ask your admin to connect an AI key in Settings → AI assistant"} for full answers.</p>;
}

function Chat() {
  const qc = useQueryClient(); const { me } = useAccess(); const path = usePathname();
  const chat = useAiChat();
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: () => api.get<{ used: number; limit: number | null }>("/api/v1/ai/usage") });
  const convs = useQuery({ queryKey: ["ai-convs"], queryFn: () => api.get<{ id: string; title: string }[]>("/api/v1/ai/conversations") });
  const send = (m: string) => chat.send(m, pageContext(path));
  const u = usage.data; const pct = u?.limit ? (u.used / u.limit) * 100 : 0;
  return (
    <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-4">
        <Button className="w-full" variant="secondary" onClick={chat.reset}><Plus /> New chat</Button>
        <Card className="p-4"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-subtle">AI usage this month</p>{u ? (u.limit ? <><p className="tabular text-xl font-semibold">{u.used}<span className="text-sm font-normal text-fg-muted"> / {u.limit}</span></p><Progress value={u.used} max={u.limit} tone={pct > 90 ? "danger" : pct > 70 ? "warning" : "primary"} className="mt-2" label="AI usage" />{pct > 80 && <Link href="/app/billing" className="mt-2 block text-xs font-medium text-primary hover:underline">Running low? Upgrade →</Link>}</> : <p className="text-sm text-fg-muted"><span className="tabular text-xl font-semibold text-fg">{u.used}</span> actions · fair use</p>) : <Skeleton className="h-10" />}</Card>
        <div className="hidden lg:block"><p className="mb-2 flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle"><History className="size-3.5" /> History</p>
          <ul className="space-y-0.5">{convs.data?.map((c) => <li key={c.id} className="group flex items-center"><button onClick={() => chat.open(c.id)} className={cn("flex-1 truncate rounded-lg px-3 py-2 text-left text-[13px]", chat.id === c.id ? "bg-primary-soft font-medium text-primary" : "text-fg-muted hover:bg-surface-hover")}>{c.title}</button><button aria-label="Delete conversation" onClick={async () => { await api.delete(`/api/v1/ai/conversations/${c.id}`); qc.invalidateQueries({ queryKey: ["ai-convs"] }); if (chat.id === c.id) chat.reset(); }} className="rounded p-1 text-fg-subtle opacity-0 hover:text-danger group-hover:opacity-100"><Trash2 className="size-3.5" /></button></li>)}{convs.data?.length === 0 && <li className="px-3 text-xs text-fg-subtle">No conversations yet</li>}</ul></div>
      </aside>
      <Card className="flex min-h-[560px] flex-col overflow-hidden" style={{ height: "calc(100dvh - 300px)" }}>
        <div className="flex-1 overflow-y-auto p-5 sm:p-8" aria-live="polite">
          {chat.msgs.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
              <span className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary"><Sparkles className="size-7" /></span>
              <h2 className="text-2xl font-semibold tracking-tight">Hi {me?.user.name.split(" ")[0]}, what can I help with?</h2><p className="mt-2 text-fg-muted">Ask about your leads, flats and team, or tell me what to do. I show you every change before it happens.</p>
              <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-border bg-surface p-3.5 text-left text-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary-soft/40 hover:shadow-sm">{s}</button>)}</div>
            </div>
          ) : <Messages msgs={chat.msgs} busy={chat.busy} />}
        </div>
        <div className="border-t border-border bg-surface-2 p-3 sm:p-4"><div className="mx-auto max-w-3xl"><Composer onSend={send} busy={chat.busy} placeholder="Ask about leads, flats, visits… or tell me what to do" /></div></div>
      </Card>
    </div>
  );
}

const TABS = ["chat", "day", "insights"];

function AIPageInner() {
  const { has, can } = useAccess();
  const sp = useSearchParams(); const router = useRouter(); const path = usePathname();
  const tab = TABS.includes(sp.get("tab") ?? "") ? sp.get("tab")! : "chat";
  const setTab = (t: string) => { const q = new URLSearchParams(sp.toString()); if (t === "chat") q.delete("tab"); else q.set("tab", t); if (t !== "day") q.delete("team"); const s = q.toString(); router.replace(s ? `${path}?${s}` : path, { scroll: false }); };
  if (!has("ai_assistant") || !can("ai.use")) return <PageContainer><PageHeader title="AI Assistant" /><ErrorState kind="permission" title={!has("ai_assistant") ? "The AI assistant isn't in your plan" : "You don't have access to the AI assistant"} description={!has("ai_assistant") ? "Upgrade to ask questions about your pipeline, draft emails and get next-best-actions." : "Ask a workspace admin to enable it for your role."} action={!has("ai_assistant") ? <Button asChild><Link href="/app/billing">See plans</Link></Button> : undefined} /></PageContainer>;
  return (
    <PageContainer wide>
      <PageHeader title={<span className="flex flex-wrap items-center gap-2.5">AI Assistant <ModeBadge /></span>} description="Ask in plain words, in English or Hindi. Answers come from your workspace data only." />
      <BasicNote />
      <Tabs value={tab} onValueChange={setTab}><TabsList className="mb-6"><TabsTrigger value="chat"><MessageSquare className="size-4" /> Ask</TabsTrigger><TabsTrigger value="day"><Sun className="size-4" /> My day</TabsTrigger><TabsTrigger value="insights"><Sparkles className="size-4" /> Insights</TabsTrigger></TabsList>
        <TabsContent value="chat"><Chat /></TabsContent><TabsContent value="day"><MyDay /></TabsContent><TabsContent value="insights"><Insights /></TabsContent></Tabs>
    </PageContainer>
  );
}

export default function AIPage() { return <Suspense><AIPageInner /></Suspense>; }
