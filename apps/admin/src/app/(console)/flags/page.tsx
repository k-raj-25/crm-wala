"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Dialog, DialogContent, DialogFooter, ErrorState, Field, Input, NativeSelect, SkeletonRows, Switch, useDebounce, useToast } from "@crm/ui";
import { PageHeader } from "@/components/bits";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type Flag = { key: string; name: string; description: string | null; enabled: boolean; rollout_percent: number; overrides: { workspace_id: string; workspace: string; enabled: boolean }[] };

export default function Page() {
  const q = useQuery({ queryKey: ["flags"], queryFn: () => api.get<Flag[]>(`${A}/feature-flags`) });
  const can = useCan(); const toast = useToast(); const qc = useQueryClient();
  const [addFor, setAddFor] = useState<Flag | null>(null);
  const patch = useMutation({
    mutationFn: ({ key, body }: { key: string; body: Record<string, unknown> }) => api.patch(`${A}/feature-flags/${key}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["flags"] }), onError: (e) => toast.error((e as Error).message),
  });
  const editable = can();
  return (
    <>
      <PageHeader title="Feature flags" description="Kill-switches and gradual rollouts. A flag can also be forced on or off for individual workspaces." />
      {q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} /> : q.isLoading ? <SkeletonRows rows={5} /> : (
        <div className="space-y-3">
          {q.data?.map((f) => <FlagRow key={f.key} f={f} editable={editable} onPatch={(body) => patch.mutate({ key: f.key, body })} onAdd={() => setAddFor(f)} />)}
          {!q.data?.length && <Card className="p-8 text-center text-sm text-fg-muted">No feature flags defined.</Card>}
        </div>
      )}
      <OverrideDialog flag={addFor} onClose={() => setAddFor(null)} />
    </>
  );
}

function FlagRow({ f, editable, onPatch, onAdd }: { f: Flag; editable: boolean; onPatch: (b: Record<string, unknown>) => void; onAdd: () => void }) {
  const [pct, setPct] = useState(String(f.rollout_percent));
  const dirty = +pct !== f.rollout_percent && pct !== "" && +pct >= 0 && +pct <= 100;
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0"><p className="font-medium">{f.name} <code className="ml-1 rounded bg-bg-subtle px-1.5 py-0.5 text-xs text-fg-muted">{f.key}</code></p>{f.description && <p className="text-sm text-fg-muted">{f.description}</p>}</div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-fg-muted"><label htmlFor={`pct-${f.key}`}>Rollout</label>
            <Input id={`pct-${f.key}`} type="number" min={0} max={100} className="h-8 w-20" value={pct} disabled={!editable} onChange={(e) => setPct(e.target.value)} />%
            {dirty && <Button size="xs" onClick={() => onPatch({ rollout_percent: +pct })}>Save</Button>}</div>
          <Switch checked={f.enabled} disabled={!editable} onCheckedChange={(c) => onPatch({ enabled: c })} aria-label={`${f.name} enabled`} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <span className="text-xs text-fg-subtle">Workspace overrides</span>
        {f.overrides.map((o) => (
          <Badge key={o.workspace_id} tone={o.enabled ? "success" : "danger"} className="gap-1.5 pr-1">{o.workspace}: {o.enabled ? "on" : "off"}
            {editable && <button aria-label={`Remove override for ${o.workspace}`} className="rounded-full p-0.5 hover:bg-black/10" onClick={() => onPatch({ workspace_override: { workspace_id: o.workspace_id, enabled: null } })}><X className="size-3" /></button>}</Badge>))}
        {!f.overrides.length && <span className="text-xs text-fg-subtle">none</span>}
        {editable && <Button size="xs" variant="ghost" onClick={onAdd}><Plus /> Add</Button>}
      </div>
    </Card>
  );
}

function OverrideDialog({ flag, onClose }: { flag: Flag | null; onClose: () => void }) {
  const [term, setTerm] = useState(""); const [ws, setWs] = useState(""); const [on, setOn] = useState("true");
  const dq = useDebounce(term, 250);
  const toast = useToast(); const qc = useQueryClient();
  const res = useQuery({ queryKey: ["ws-search", dq], queryFn: () => api.page<{ id: string; name: string }>(`${A}/workspaces`, { q: dq, per_page: 8 }), enabled: !!flag });
  const m = useMutation({
    mutationFn: () => api.patch(`${A}/feature-flags/${flag!.key}`, { workspace_override: { workspace_id: ws, enabled: on === "true" } }),
    onSuccess: () => { toast.success("Override saved"); qc.invalidateQueries({ queryKey: ["flags"] }); setWs(""); setTerm(""); onClose(); }, onError: (e) => toast.error((e as Error).message),
  });
  return (
    <Dialog open={!!flag} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Override “${flag?.name}”`} description="Force this flag on or off for a single workspace, regardless of rollout." size="sm">
        <div className="space-y-4">
          <Field label="Find workspace"><Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search by name…" autoFocus /></Field>
          <Field label="Workspace"><NativeSelect value={ws} onChange={(e) => setWs(e.target.value)} size={5}><option value="" disabled>Select…</option>{res.data?.data.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</NativeSelect></Field>
          <Field label="State"><NativeSelect value={on} onChange={(e) => setOn(e.target.value)}><option value="true">Force on</option><option value="false">Force off</option></NativeSelect></Field>
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button disabled={!ws} loading={m.isPending} onClick={() => m.mutate()}>Save override</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
