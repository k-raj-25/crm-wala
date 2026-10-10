"use client";
import { CalendarPlus } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Switch, cn } from "@crm/ui";
import { CalendarView, KINDS } from "@/components/calendar/calendar";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { useUI } from "@/components/shell/ui-context";
import { useAccess } from "@/lib/queries";

export default function CalendarPage() {
  const ui = useUI(); const { can } = useAccess();
  const [mine, setMine] = React.useState(true);
  const [kinds, setKinds] = React.useState(new Set(Object.keys(KINDS)));
  const toggle = (k: string) => setKinds((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  return (
    <PageContainer wide>
      <PageHeader title="Site Visits" description="Property visits, meetings, calls and follow-ups in one calendar."
        actions={<>{can("meetings.create") && <Button onClick={() => ui.openCreate("meeting", { kind: "site_visit" })}><CalendarPlus /> Schedule site visit</Button>}</>} />
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="flex flex-wrap gap-2">{Object.entries(KINDS).map(([k, v]) => <button key={k} aria-pressed={kinds.has(k)} onClick={() => toggle(k)} className={cn("flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors", kinds.has(k) ? "border-transparent" : "border-border text-fg-subtle")} style={kinds.has(k) ? { background: `color-mix(in srgb, ${v.color} 14%, transparent)`, color: `color-mix(in srgb, ${v.color} 70%, var(--fg))` } : undefined}><span className="size-2 rounded-full" style={{ background: v.color }} />{v.label}</button>)}</div>
        <label className="ml-auto flex items-center gap-2 text-sm text-fg-muted"><Switch checked={mine} onCheckedChange={setMine} aria-label="Only my events" />Only mine</label>
        <Link href="/app/integrations" className="text-[13px] font-medium text-primary hover:underline">Sync with Google Calendar →</Link>
      </div>
      <CalendarView mine={mine} kinds={kinds} />
    </PageContainer>
  );
}
