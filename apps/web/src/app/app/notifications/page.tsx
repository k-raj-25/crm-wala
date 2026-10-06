"use client";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Settings } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Button, Card, EmptyState, Segmented, SkeletonRows } from "@crm/ui";
import { PageContainer, PageHeader } from "@/components/shell/page";
import { NotificationRow, useOpenNotification } from "@/components/shell/notifications";
import { api } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

export default function NotificationsPage() {
  const [f, setF] = React.useState<"all" | "unread">("all"); const qc = useQueryClient(); const open = useOpenNotification();
  const q = useInfiniteQuery({ queryKey: ["notifications", "page", f], initialPageParam: 1, queryFn: ({ pageParam }) => api.page<NotificationItem>("/api/v1/notifications", { page: pageParam, per_page: 25, unread: f === "unread" ? "true" : undefined }), getNextPageParam: (l) => (l.meta.page < l.meta.pages ? l.meta.page + 1 : undefined) });
  const items = q.data?.pages.flatMap((p) => p.data) ?? [];
  return (
    <PageContainer>
      <PageHeader title="Notifications" description="Leads, assignments, mentions, reminders and billing alerts."
        actions={<><Segmented size="sm" value={f} onChange={setF} options={[{ value: "all", label: "All" }, { value: "unread", label: "Unread" }]} /><Button variant="secondary" onClick={async () => { await api.post("/api/v1/notifications/read-all"); qc.invalidateQueries({ queryKey: ["notifications"] }); }}>Mark all read</Button><Button variant="ghost" asChild><Link href="/app/settings/notifications"><Settings /> Preferences</Link></Button></>} />
      <Card className="overflow-hidden">{q.isLoading ? <div className="p-6"><SkeletonRows /></div> : !items.length ? <EmptyState icon={<Bell />} title={f === "unread" ? "No unread notifications" : "You're all caught up"} description="We'll let you know when something needs your attention." /> : <div className="divide-y divide-border">{items.map((n) => <NotificationRow key={n.id} n={n} onOpen={open} />)}</div>}</Card>
      {q.hasNextPage && <div className="mt-4 flex justify-center"><Button variant="secondary" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>Load more</Button></div>}
    </PageContainer>
  );
}
