"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Avatar, Badge, Button, Card, Dialog, DialogContent, DialogFooter, ErrorState, Field, Input, NativeSelect, SkeletonRows, Table, TBody, TD, TH, THead, TR, formatDate, useToast } from "@crm/ui";
import { PageHeader, StatusBadge } from "@/components/bits";
import { useStepUp } from "@/components/step-up";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";
import type { Admin } from "@/lib/types";

const ROLES = { superadmin: "Full access, including deletes and settings", support: "Users, impersonation, trial extensions", finance: "Plans, coupons, credits and refunds" } as const;

export default function Page() {
  const can = useCan();
  const q = useQuery({ queryKey: ["admins"], queryFn: () => api.get<Admin[]>(`${A}/admins`), enabled: can() });
  const [open, setOpen] = useState(false);
  if (!can()) return <ErrorState kind="permission" />;
  return (
    <>
      <PageHeader title="Admin team" description="People with access to this console." actions={<Button onClick={() => setOpen(true)}><Plus /> Add admin</Button>} />
      <div className="mb-4 grid gap-3 md:grid-cols-3">{Object.entries(ROLES).map(([r, d]) => <Card key={r} className="p-4"><p className="flex items-center gap-2 text-sm font-medium capitalize"><ShieldCheck className="size-4 text-primary" />{r}</p><p className="mt-1 text-[13px] text-fg-muted">{d}</p></Card>)}</div>
      <Card className="overflow-x-auto">{q.isError ? <ErrorState compact kind="unavailable" onRetry={() => q.refetch()} /> : q.isLoading ? <div className="p-4"><SkeletonRows rows={3} /></div> : (
        <Table><THead><TR><TH>Admin</TH><TH>Role</TH><TH>2FA</TH><TH>Status</TH><TH>Last login</TH></TR></THead>
          <TBody>{q.data?.map((a) => <TR key={a.id}><TD><div className="flex items-center gap-3"><Avatar name={a.name} size={30} /><div><p className="font-medium">{a.name}</p><p className="text-xs text-fg-muted">{a.email}</p></div></div></TD><TD className="capitalize">{a.role}</TD><TD>{a.mfa_enabled ? <Badge tone="success">Enabled</Badge> : <Badge tone="warning">Not set up</Badge>}</TD><TD><StatusBadge status={a.status} /></TD><TD className="text-fg-muted">{a.last_login_at ? formatDate(a.last_login_at, "datetime") : "Never"}</TD></TR>)}</TBody></Table>)}</Card>
      <AddDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function AddDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const stepUp = useStepUp(); const toast = useToast(); const qc = useQueryClient();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "support" });
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => stepUp(() => api.post(`${A}/admins`, f)),
    onSuccess: () => { toast.success("Admin created", "They'll set up two-factor on first sign-in."); qc.invalidateQueries({ queryKey: ["admins"] }); setF({ name: "", email: "", password: "", role: "support" }); onClose(); }, onError: (e) => setErr((e as Error).message),
  });
  const set = (k: keyof typeof f, v: string) => setF((s) => ({ ...s, [k]: v }));
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Add an admin" description="Share the temporary password through a secure channel." size="sm">
        <div className="space-y-4">
          <Field label="Full name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Email"><Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="Temporary password" hint="12+ characters with letters and numbers."><Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} /></Field>
          <Field label="Role"><NativeSelect value={f.role} onChange={(e) => set("role", e.target.value)}>{Object.keys(ROLES).map((r) => <option key={r} value={r}>{r}</option>)}</NativeSelect></Field>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </div>
        <DialogFooter><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={!f.name || !f.email || f.password.length < 12} onClick={() => { setErr(null); m.mutate(); }}>Create admin</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
