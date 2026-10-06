"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorState, Field, Input, Skeleton, Switch, useToast } from "@crm/ui";
import { PageHeader } from "@/components/bits";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type S = { key: string; value: Record<string, unknown>; description: string };

export default function Page() {
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api.get<S[]>(`${A}/settings`) });
  const can = useCan();
  const by = Object.fromEntries((q.data ?? []).map((s) => [s.key, s]));
  return (
    <>
      <PageHeader title="Platform settings" description="Global behaviour. Changes take effect immediately and are audit-logged." />
      {q.isError ? <ErrorState kind="unavailable" onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-80" /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <NumberSetting s={by.trial_days} label="Free trial length" unit="days" editable={can()} />
          <NumberSetting s={by.grace_days} label="Failed-payment grace period" unit="days" editable={can()} />
          <TaxSetting s={by.tax} editable={can()} />
          <ToggleSetting s={by.signups_enabled} label="Allow new signups" invert={false} editable={can()} />
          <ToggleSetting s={by.maintenance_mode} label="Maintenance mode" invert={false} danger editable={can()} />
        </div>
      )}
    </>
  );
}

function useSave(key: string) {
  const toast = useToast(); const qc = useQueryClient();
  return useMutation({ mutationFn: (value: Record<string, unknown>) => api.put(`${A}/settings/${key}`, { value }), onSuccess: () => { toast.success("Setting saved"); qc.invalidateQueries({ queryKey: ["settings"] }); }, onError: (e) => toast.error((e as Error).message) });
}

function NumberSetting({ s, label, unit, editable }: { s?: S; label: string; unit: string; editable: boolean }) {
  const [v, setV] = useState(String(s?.value.value ?? ""));
  const save = useSave(s?.key ?? "");
  if (!s) return null;
  const n = Number(v); const valid = v !== "" && Number.isInteger(n) && n >= 0 && n <= 365;
  return (
    <Card className="p-5"><Field label={label} hint={s.description} error={valid || v === "" ? undefined : "Whole number between 0 and 365"}>
      <div className="flex items-center gap-2"><Input type="number" min={0} max={365} className="w-28" value={v} disabled={!editable} onChange={(e) => setV(e.target.value)} /><span className="text-sm text-fg-muted">{unit}</span>
        {editable && <Button className="ml-auto" disabled={!valid || n === s.value.value} loading={save.isPending} onClick={() => save.mutate({ value: n })}>Save</Button>}</div></Field></Card>
  );
}

function TaxSetting({ s, editable }: { s?: S; editable: boolean }) {
  const [name, setName] = useState(String(s?.value.name ?? "")); const [pct, setPct] = useState(String(s?.value.percent ?? ""));
  const save = useSave("tax");
  if (!s) return null;
  const p = Number(pct); const valid = pct !== "" && p >= 0 && p <= 100 && name.trim().length > 0;
  return (
    <Card className="p-5"><p className="mb-1 text-sm font-medium">Tax</p><p className="mb-3 text-[13px] text-fg-muted">{s.description}</p>
      <div className="flex flex-wrap items-end gap-3"><Field label="Name"><Input className="w-32" value={name} disabled={!editable} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Percent"><Input type="number" min={0} max={100} step="0.01" className="w-28" value={pct} disabled={!editable} onChange={(e) => setPct(e.target.value)} /></Field>
        {editable && <Button className="ml-auto" disabled={!valid || (name === s.value.name && p === s.value.percent)} loading={save.isPending} onClick={() => save.mutate({ name, percent: p })}>Save</Button>}</div></Card>
  );
}

function ToggleSetting({ s, label, danger, editable }: { s?: S; label: string; invert: boolean; danger?: boolean; editable: boolean }) {
  const save = useSave(s?.key ?? "");
  if (!s) return null;
  const on = Boolean(s.value.value);
  return (
    <Card className={`flex items-center justify-between gap-4 p-5 ${danger && on ? "border-warning" : ""}`}>
      <div><p className="text-sm font-medium">{label}</p><p className="text-[13px] text-fg-muted">{s.description}</p></div>
      <Switch checked={on} disabled={!editable || save.isPending} onCheckedChange={(c) => save.mutate({ value: c })} aria-label={label} />
    </Card>
  );
}
