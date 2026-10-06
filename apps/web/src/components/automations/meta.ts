import { Bell, CheckSquare, Clock, FileText, Globe, Mail, Tag, ToggleRight, UserPlus, Zap } from "lucide-react";

export type Field = { key: string; label: string; type: "text" | "textarea" | "number" | "select" | "user"; options?: string[]; default?: unknown };
export type Meta = { triggers: { key: string; label: string; config: { key: string; label: string; type: string }[] }[]; actions: { key: string; label: string; fields: Field[] }[] };
export type Step = { id: string; action_type: string; config: Record<string, unknown> };
export type Graph = { nodes: { id: string; type: "trigger" | "action"; position: { x: number; y: number }; data: Record<string, unknown> }[]; edges: { id: string; source: string; target: string }[] };

export const ACTION_ICONS: Record<string, React.ElementType> = { send_email: Mail, create_task: CheckSquare, assign_user: UserPlus, add_tag: Tag, change_status: ToggleRight, send_notification: Bell, webhook: Globe, delay: Clock, create_activity: FileText };
export const ACTION_COLORS: Record<string, string> = { send_email: "var(--series-2)", create_task: "var(--series-7)", assign_user: "var(--series-3)", add_tag: "var(--series-5)", change_status: "var(--series-1)", send_notification: "var(--series-4)", webhook: "var(--fg-muted)", delay: "var(--series-4)", create_activity: "var(--series-6)" };
export const TRIGGER_ICON = Zap;

export function toGraph(trigger: string, triggerConfig: Record<string, unknown>, steps: Step[]): Graph {
  const nodes: Graph["nodes"] = [{ id: "trigger", type: "trigger", position: { x: 0, y: 0 }, data: { trigger_type: trigger, config: triggerConfig } }, ...steps.map((s, i) => ({ id: s.id, type: "action" as const, position: { x: 0, y: (i + 1) * 150 }, data: { action_type: s.action_type, config: s.config } }))];
  const ids = nodes.map((n) => n.id);
  return { nodes, edges: ids.slice(1).map((id, i) => ({ id: `e${i}`, source: ids[i], target: id })) };
}
export function fromGraph(g: Graph): { trigger: string; triggerConfig: Record<string, unknown>; steps: Step[] } {
  const nodes = new Map(g.nodes.map((n) => [n.id, n])); const next = new Map(g.edges.map((e) => [e.source, e.target]));
  const t = g.nodes.find((n) => n.type === "trigger")!; const steps: Step[] = []; let cur = next.get(t.id);
  while (cur) { const n = nodes.get(cur)!; steps.push({ id: n.id, action_type: n.data.action_type as string, config: (n.data.config as Record<string, unknown>) ?? {} }); cur = next.get(cur); }
  return { trigger: t.data.trigger_type as string, triggerConfig: (t.data.config as Record<string, unknown>) ?? {}, steps };
}

export const TEMPLATES: { name: string; description: string; trigger: string; steps: Omit<Step, "id">[] }[] = [
  { name: "Welcome & follow up new leads", description: "Assign, email, create a task, wait 2 days, then remind.", trigger: "lead.created", steps: [
    { action_type: "assign_user", config: { strategy: "round_robin" } }, { action_type: "send_email", config: { to: "record", subject: "Thanks for reaching out, {{first_name}}", body: "Hi {{first_name}},\n\nThanks for your interest — we'll be in touch shortly.\n\nBest," } },
    { action_type: "create_task", config: { title: "Call {{first_name}}", due_in_days: 1, priority: "high" } }, { action_type: "delay", config: { amount: 2, unit: "days" } }, { action_type: "send_notification", config: { title: "Reminder: follow up with {{name}}", body: "It's been 2 days.", to: "owner" } }] },
  { name: "Celebrate won deals", description: "Notify admins and log an activity whenever a deal is won.", trigger: "deal.stage_changed", steps: [{ action_type: "send_notification", config: { title: "🎉 Deal won: {{name}}", body: "Great work, team!", to: "admins" } }, { action_type: "create_activity", config: { title: "Deal won — automation notified the team" } }] },
  { name: "Tag & route form submissions", description: "Tag website leads and create a same-day task.", trigger: "form.submitted", steps: [{ action_type: "add_tag", config: { tag: "inbound" } }, { action_type: "create_task", config: { title: "Respond to {{name}}", due_in_days: 0, priority: "high" } }] },
];
export const uid = () => Math.random().toString(36).slice(2, 9);
