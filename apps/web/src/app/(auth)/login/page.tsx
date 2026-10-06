"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, Button, Field, Input } from "@crm/ui";
import { AuthShell, GoogleButton, OrDivider, PasswordInput } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";
import { applyApiErrors } from "@/lib/forms";
import { keys } from "@/lib/queries";
import type { Me } from "@/lib/types";

const schema = z.object({ email: z.string().email("Enter a valid email"), password: z.string().min(1, "Enter your password") });
type V = z.infer<typeof schema>;
export const dynamic = "force-dynamic";

function LoginForm() {
  const router = useRouter();
  const sp = useSearchParams();
  const qc = useQueryClient();
  const next = sp.get("next");
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api.get<{ google_enabled: boolean }>("/api/v1/auth/config"), staleTime: Infinity });
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<V>({ resolver: zodResolver(schema) });
  const [formError, setFormError] = useState<string | null>(null);
  const [mfa, setMfa] = useState<{ token: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const finish = async (me: Me) => {
    qc.setQueryData(keys.me, me);
    const dest = next && next.startsWith("/") ? next : me.workspace && !me.workspace.onboarding_completed_at && me.role?.key === "owner" ? "/onboarding" : "/app";
    router.replace(dest);
  };
  const onSubmit = async (v: V) => {
    setFormError(null);
    try {
      const r = await api.post<Me & { mfa_required?: boolean; mfa_token?: string }>("/api/v1/auth/login", v);
      if (r.mfa_required && r.mfa_token) setMfa({ token: r.mfa_token });
      else await finish(r);
    } catch (e) { setFormError(applyApiErrors(e, setError, ["email", "password"])); }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setFormError(null);
    try { await finish(await api.post<Me>("/api/v1/auth/login/2fa", { mfa_token: mfa!.token, code })); }
    catch (err) { setFormError((err as ApiError).message); if ((err as ApiError).code === "mfa_expired") setMfa(null); }
    finally { setBusy(false); }
  };

  if (mfa) return (
    <AuthShell title="Two-step verification" subtitle="Enter the 6-digit code from your authenticator app.">
      <form onSubmit={verify} className="space-y-4">
        <Field label="Authentication code"><Input inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" className="text-center text-lg tracking-[0.4em]" /></Field>
        {formError && <p role="alert" className="flex items-center gap-2 text-sm text-danger"><AlertCircle className="size-4" />{formError}</p>}
        <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length < 6}>Verify and sign in</Button>
        <button type="button" onClick={() => { setMfa(null); setCode(""); setFormError(null); }} className="mx-auto flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg"><ArrowLeft className="size-3.5" /> Back to sign in</button>
      </form>
    </AuthShell>
  );

  const err = sp.get("error");
  const banner = sp.get("expired") ? "Your session expired — please sign in again." : err ? ({ oauth_failed: "Google sign-in failed. Please try again.", oauth_state: "Google sign-in expired. Please try again.", suspended: "This account has been suspended.", signups_disabled: "New signups are currently disabled." } as Record<string, string>)[err] ?? "Sign-in failed." : null;
  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your workspace." footer={<>New to CRM Wala? <Link href="/signup" className="font-medium text-primary hover:underline">Start your free trial</Link></>}>
      {banner && <div role="alert" className="mb-5 flex items-center gap-2 rounded-lg bg-warning-soft px-3.5 py-2.5 text-sm text-warning"><AlertCircle className="size-4 shrink-0" />{banner}</div>}
      {cfg.data?.google_enabled && <><GoogleButton /><OrDivider /></>}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Field label="Work email" error={errors.email?.message}><Input type="email" autoComplete="email" autoFocus placeholder="you@company.com" {...register("email")} /></Field>
        <Field label={<span className="flex w-full items-center justify-between">Password<Link href="/forgot-password" className="text-xs font-normal text-primary hover:underline" tabIndex={-1}>Forgot password?</Link></span>} error={errors.password?.message}><PasswordInput autoComplete="current-password" {...register("password")} /></Field>
        {formError && <p role="alert" className="flex items-center gap-2 text-sm text-danger"><AlertCircle className="size-4 shrink-0" />{formError}</p>}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>Sign in</Button>
      </form>
    </AuthShell>
  );
}
export default function Page() { return <Suspense><LoginForm /></Suspense>; }
