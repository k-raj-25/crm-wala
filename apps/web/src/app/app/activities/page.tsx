"use client";
import * as React from "react";
import { Card, CardBody, cn } from "@crm/ui";
import { MemberSelect } from "@/components/forms/fields";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { Timeline } from "@/components/records/timeline";

const TYPES = [["email", "Emails"], ["call", "Calls"], ["meeting", "Meetings"], ["note", "Notes"], ["stage_changed,won,lost", "Deal changes"], ["task,task_completed", "Tasks"], ["created,converted", "New records"]] as const;
export default function ActivitiesPage() {
  const [types, setTypes] = React.useState<string | null>(null); const [user, setUser] = React.useState<string | null>(null);
  return (
    <PageContainer>
      <PageHeader title="Activities" description="Everything that's happened across your workspace, newest first." />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <button onClick={() => setTypes(null)} className={cn("rounded-full px-3.5 py-1.5 text-[13px] font-medium", !types ? "bg-fg text-bg" : "text-fg-muted hover:bg-surface-hover")}>All</button>
        {TYPES.map(([k, l]) => <button key={k} onClick={() => setTypes(types === k ? null : k)} className={cn("rounded-full px-3.5 py-1.5 text-[13px] font-medium", types === k ? "bg-fg text-bg" : "text-fg-muted hover:bg-surface-hover")}>{l}</button>)}
        <div className="ml-auto w-48"><MemberSelect value={user} onChange={setUser} noneLabel="Everyone" size="sm" /></div>
      </div>
      <Card><CardBody><Timeline types={types ?? undefined} userId={user ?? undefined} showRelated /></CardBody></Card>
    </PageContainer>
  );
}
