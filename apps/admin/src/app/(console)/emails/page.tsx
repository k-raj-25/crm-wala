"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Mail, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, Skeleton, Textarea, cn, timeAgo, useToast } from "@crm/ui";
import { PageHeader } from "@/components/bits";
import { A, api } from "@/lib/api";
import { useCan } from "@/lib/hooks";

type T = { key: string; name: string; subject: string; body_html: string; variables: string[]; updated_at: string };

export default function Page() {
  const list = useQuery({ queryKey: ["templates"], queryFn: () => api.get<T[]>(`${A}/email-templates`) });
  const [sel, setSel] = useState<string | null>(null);
  const cur = list.data?.find((t) => t.key === (sel ?? list.data?.[0]?.key));
  return (
    <>
      <PageHeader title="Email templates" description="Transactional emails sent by the platform. Use {{ variables }} — syntax is validated on save." />
      {list.isError ? <ErrorState kind="unavailable" onRetry={() => list.refetch()} /> : !list.data ? <Skeleton className="h-96" /> : !list.data.length ? <EmptyState title="No templates" /> : (
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          <Card className="h-fit p-2"><ul>{list.data.map((t) => <li key={t.key}><button onClick={() => setSel(t.key)} className={cn("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm", cur?.key === t.key ? "bg-primary-soft font-medium text-primary" : "text-fg-muted hover:bg-surface-hover")}><Mail className="size-4 shrink-0" /><span className="truncate">{t.name}</span></button></li>)}</ul></Card>
          {cur && <Editor key={cur.key} t={cur} />}
        </div>
      )}
    </>
  );
}

function Editor({ t }: { t: T }) {
  const can = useCan(); const toast = useToast(); const qc = useQueryClient();
  const [subject, setSubject] = useState(t.subject); const [body, setBody] = useState(t.body_html);
  const [preview, setPreview] = useState<{ subject: string; html: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const dirty = subject !== t.subject || body !== t.body_html;
  const canEdit = can();

  const loadPreview = useMutation({ mutationFn: () => api.get<{ subject: string; html: string }>(`${A}/email-templates/${t.key}/preview`), onSuccess: setPreview, onError: (e) => toast.error((e as Error).message) });
  useEffect(() => { loadPreview.mutate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [t.updated_at]);
  const save = useMutation({
    mutationFn: () => api.put(`${A}/email-templates/${t.key}`, { subject, body_html: body }),
    onSuccess: () => { setErr(null); toast.success("Template saved"); qc.invalidateQueries({ queryKey: ["templates"] }); }, onError: (e) => setErr((e as Error).message),
  });
  const test = useMutation({ mutationFn: () => api.post<{ to: string; sent: boolean }>(`${A}/email-templates/${t.key}/send-test`), onSuccess: (r) => (r.sent ? toast.success(`Test sent to ${r.to}`) : toast.error("Email provider rejected the test")), onError: (e) => toast.error((e as Error).message) });

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="space-y-4 p-5">
        <div className="flex items-start justify-between"><div><h2 className="font-semibold">{t.name}</h2><p className="text-xs text-fg-subtle">Updated {timeAgo(t.updated_at)}</p></div></div>
        <div className="flex flex-wrap gap-1.5">{t.variables.map((v) => <Badge key={v} tone="outline"><code>{`{{ ${v} }}`}</code></Badge>)}</div>
        <Field label="Subject"><Input value={subject} disabled={!canEdit} onChange={(e) => setSubject(e.target.value)} /></Field>
        <Field label="HTML body"><Textarea rows={16} className="font-mono text-[13px]" value={body} disabled={!canEdit} onChange={(e) => setBody(e.target.value)} spellCheck={false} /></Field>
        {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        <div className="flex flex-wrap gap-2">
          {canEdit && <Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}><Save /> Save changes</Button>}
          {canEdit && <Button variant="secondary" loading={test.isPending} disabled={dirty} onClick={() => test.mutate()} title={dirty ? "Save before sending a test" : undefined}><Mail /> Send test to me</Button>}
          <Button variant="ghost" onClick={() => loadPreview.mutate()} loading={loadPreview.isPending} disabled={dirty}><Eye /> Refresh preview</Button>
        </div>
        {dirty && <p className="text-xs text-fg-subtle">Preview and test emails use the last saved version.</p>}
      </Card>
      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-3"><p className="text-xs text-fg-subtle">Subject</p><p className="text-sm font-medium">{preview?.subject ?? "…"}</p></div>
        {/* sandbox with no allow-scripts: previews can never execute template content */}
        <iframe title="Email preview" sandbox="" srcDoc={preview?.html ?? ""} className="h-[560px] w-full bg-white" />
      </Card>
    </div>
  );
}
