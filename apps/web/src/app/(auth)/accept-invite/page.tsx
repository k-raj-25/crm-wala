"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorState, Field, Input, Spinner } from "@crm/ui";
import { AuthShell, PasswordInput, StrengthMeter } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Me } from "@/lib/types";

export const dynamic = "force-dynamic";
function Inner() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter(); const qc = useQueryClient();
  const info = useQuery({ queryKey: ["invite", token], enabled: !!token, retry: false, queryFn: () => api.get<{ email: string; workspace: string; role: string; user_exists: boolean }>(`/api/v1/auth/invitations/${token}`) });
  const [name, setName] = useState(""); const [password, setPassword] = useState(""); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const accept = async () => {
    setBusy(true); setErr(null);
    try { const me = await api.post<Me>("/api/v1/auth/invitations/accept", { token, name, password }); qc.setQueryData(keys.me, me); router.replace("/app"); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  if (info.isLoading) return <AuthShell title="Loading invitation…"><div className="flex justify-center py-8"><Spinner className="size-8 text-primary" /></div></AuthShell>;
  if (info.isError || !info.data) return <AuthShell title="Invitation unavailable"><ErrorState compact kind="generic" title="This invitation is invalid or has expired" description="Ask the person who invited you to send a new invitation." action={<Button asChild variant="secondary"><Link href="/login">Go to sign in</Link></Button>} /></AuthShell>;
  const d = info.data;
  return (
    <AuthShell title={`Join ${d.workspace}`} subtitle={<>You've been invited as <strong className="text-fg">{d.role}</strong> ({d.email}).</>}>
      {d.user_exists ? (
        <div className="space-y-4"><p className="text-sm text-fg-muted">You already have a CRM Wala account with this email. Sign in, then open this link again to accept.</p>
          <Button asChild size="lg" className="w-full"><Link href={`/login?next=${encodeURIComponent(`/accept-invite?token=${token}`)}`}>Sign in to accept</Link></Button>
          <Button size="lg" variant="secondary" className="w-full" onClick={accept} loading={busy}>I'm already signed in — accept</Button>{err && <p role="alert" className="text-sm text-danger">{err}</p>}</div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); accept(); }} className="space-y-4">
          <Field label="Your name"><Input value={name} onChange={(e) => setName(e.target.value)} autoFocus required /></Field>
          <div><Field label="Create a password"><PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required /></Field><StrengthMeter value={password} /></div>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
          <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!name || password.length < 10}>Join workspace</Button>
        </form>
      )}
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
