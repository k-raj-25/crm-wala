"use client";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, AtSign, Bell, CalendarClock, CheckSquare, Handshake, Settings2, Sparkles, UserPlus, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Button, EmptyState, Popover, PopoverContent, PopoverTrigger, Skeleton, Tooltip, cn, timeAgo } from "@crm/ui";
import { api } from "@/lib/api";
import { useNotifications } from "@/lib/queries";
import type { NotificationItem } from "@/lib/types";

const ICONS: Record<string, React.ElementType> = { new_lead: UserPlus, task_assigned: CheckSquare, deal_update: Handshake, mention: AtSign, meeting_reminder: CalendarClock, automation: Workflow, payment_issue: AlertCircle, trial_ending: Sparkles, system: Settings2 };
const TONES: Record<string, string> = { payment_issue: "bg-danger-soft text-danger", trial_ending: "bg-warning-soft text-warning", new_lead: "bg-success-soft text-success", deal_update: "bg-primary-soft text-primary" };

export function NotificationRow({ n, onOpen }: { n: NotificationItem; onOpen: (n: NotificationItem) => void }) {
  const I = ICONS[n.type] ?? Bell;
  return (
    <motion.button layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} onClick={() => onOpen(n)} className={cn("flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-hover", !n.read_at && "bg-primary-soft/30")}>
      <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full", TONES[n.type] ?? "bg-bg-subtle text-fg-muted")}><I className="size-4" /></span>
      <span className="min-w-0 flex-1"><span className={cn("block text-[13px] leading-snug", !n.read_at && "font-semibold")}>{n.title}</span>{n.body && <span className="mt-0.5 block truncate text-xs text-fg-muted">{n.body}</span>}<span className="mt-1 block text-[11px] text-fg-subtle">{timeAgo(n.created_at)}</span></span>
      {!n.read_at && <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
    </motion.button>
  );
}

export function useOpenNotification() {
  const qc = useQueryClient(); const router = useRouter();
  return async (n: NotificationItem) => {
    if (!n.read_at) { api.post(`/api/v1/notifications/${n.id}/read`).then(() => qc.invalidateQueries({ queryKey: ["notifications"] })).catch(() => {}); }
    if (n.link) router.push(n.link);
  };
}

export function NotificationsPopover({ collapsed }: { collapsed?: boolean }) {
  const q = useNotifications();
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const openN = useOpenNotification();
  const unread = (q.data?.meta.unread as number) ?? 0;
  const markAll = async () => { await api.post("/api/v1/notifications/read-all"); qc.invalidateQueries({ queryKey: ["notifications"] }); };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip content="Notifications" side="right">
        <PopoverTrigger asChild>
          <Button variant="ghost" size={collapsed ? "icon" : "sm"} className={cn("relative", !collapsed && "flex-1 justify-start")} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
            <span className="relative"><Bell />{unread > 0 && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="absolute -right-1 -top-1 flex size-3.5 items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white">{unread > 9 ? "9+" : unread}</motion.span>}</span>
            {!collapsed && "Alerts"}
          </Button>
        </PopoverTrigger>
      </Tooltip>
      <PopoverContent side="right" align="end" sideOffset={12} className="w-[380px] max-w-[calc(100vw-24px)] overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-3"><h2 className="text-sm font-semibold">Notifications</h2>{unread > 0 && <button onClick={markAll} className="text-xs font-medium text-primary hover:underline">Mark all read</button>}</div>
        <div className="max-h-[420px] divide-y divide-border overflow-y-auto">
          {q.isLoading ? <div className="space-y-3 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            : !q.data?.data.length ? <EmptyState compact icon={<Bell />} title="You're all caught up" description="New leads, mentions and reminders will show up here." />
            : <AnimatePresence initial={false}>{q.data.data.map((n) => <NotificationRow key={n.id} n={n} onOpen={(x) => { setOpen(false); openN(x); }} />)}</AnimatePresence>}
        </div>
        <Link href="/app/notifications" onClick={() => setOpen(false)} className="block border-t border-border px-4 py-2.5 text-center text-[13px] font-medium text-primary hover:bg-surface-hover">View all notifications</Link>
      </PopoverContent>
    </Popover>
  );
}
