"use client";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Mail, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button, Spinner, useToast } from "@crm/ui";
import { AuthShell } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";
import { keys, useMe } from "@/lib/queries";

export const dynamic = "force-dynamic";

function Inner() {
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const token = sp.get("token");
  const me = useMe();
  const [state, setState] = useState<"idle" | "verifying" | "ok" | "bad">(token ? "verifying" : "idle");
  const [devToken, setDevToken] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => { setDevToken(sessionStorage.getItem("dev_verify_token")); }, []);
  useEffect(() => {
    if (!token) return;
    api.post("/api/v1/auth/verify-email", { token }).then(() => { setState("ok"); qc.invalidateQueries({ queryKey: keys.me }); }).catch(() => setState("bad"));
  }, [token, qc]);
  useEffect(() => { if (me.data?.user.email_verified && !token) router.replace("/app"); }, [me.data, token, router]);

  const resend = async () => {
    setSending(true);
    try { const r = await api.post<{ dev_verify_token?: string }>("/api/v1/auth/resend-verification"); if (r.dev_verify_token) { sessionStorage.setItem("dev_verify_token", r.dev_verify_token); setDevToken(r.dev_verify_token); } toast.success("Verification email sent", "Check your inbox (and spam folder)."); }
    catch (e) { toast.error("Couldn't send email", (e as Error).message); } finally { setSending(false); }
  };

  if (state === "verifying") return <AuthShell title="Verifying your email…"><div className="flex justify-center py-8"><Spinner className="size-8 text-primary" /></div></AuthShell>;
  if (state === "ok") return (
    <AuthShell title="Email verified" subtitle="Thanks — your account is secure and ready to go.">
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-success-soft text-success"><CheckCircle2 className="size-7" /></div>
      <Button size="lg" className="w-full" onClick={() => router.replace("/app")}>Continue to your workspace</Button>
    </AuthShell>
  );
  if (state === "bad") return (
    <AuthShell title="This link isn't valid" subtitle="It may have expired or already been used.">
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-danger-soft text-danger"><XCircle className="size-7" /></div>
      <Button size="lg" className="w-full" onClick={resend} loading={sending}>Send a new verification email</Button>
      <p className="mt-4 text-center text-sm text-fg-muted"><Link href="/login" className="text-primary hover:underline">Back to sign in</Link></p>
    </AuthShell>
  );
  return (
    <AuthShell title="Check your inbox" subtitle={<>We sent a verification link to <strong className="text-fg">{me.data?.user.email ?? "your email"}</strong>. Click it to activate your account.</>}>
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary"><Mail className="size-7" /></div>
      <div className="space-y-3">
        <Button variant="secondary" size="lg" className="w-full" onClick={resend} loading={sending}>Resend email</Button>
        <Button variant="ghost" size="lg" className="w-full" onClick={() => router.replace("/onboarding")}>Continue setup for now</Button>
      </div>
      {devToken && <p className="mt-6 rounded-lg border border-dashed border-border-strong p-3 text-xs text-fg-muted">Development mode: no email provider configured. <Link className="font-medium text-primary underline" href={`/verify-email?token=${devToken}`}>Open verification link</Link></p>}
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
