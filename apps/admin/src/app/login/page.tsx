"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import QRCode from "qrcode";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, Button, Field, Input, ThemeToggle } from "@crm/ui";
import { A, api } from "@/lib/api";
import type { Admin } from "@/lib/types";

const schema = z.object({ email: z.string().email("Enter a valid email"), password: z.string().min(1, "Enter your password") });
type V = z.infer<typeof schema>;
type Step = { kind: "mfa"; token: string } | { kind: "setup"; token: string; secret: string; uri: string };

function Form() {
  const router = useRouter();
  const sp = useSearchParams();
  const qc = useQueryClient();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<V>({ resolver: zodResolver(schema) });
  const [step, setStep] = useState<Step | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(sp.get("expired") ? "Your session expired — please sign in again." : null);
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [qr, setQr] = useState("");

  useEffect(() => { if (step?.kind === "setup") QRCode.toDataURL(step.uri, { margin: 1, width: 180 }).then(setQr); }, [step]);

  const done = async () => {
    await qc.invalidateQueries({ queryKey: ["admin-me"] });
    const n = sp.get("next");
    router.replace(n && n.startsWith("/") && !n.startsWith("//") ? n : "/dashboard");
  };
  const submit = async (v: V) => {
    setErr(null);
    try {
      const r = await api.post<{ admin?: Admin; mfa_required?: boolean; mfa_setup_required?: boolean; mfa_token?: string; secret?: string; otpauth_uri?: string }>(`${A}/auth/login`, v);
      if (r.mfa_setup_required) setStep({ kind: "setup", token: r.mfa_token!, secret: r.secret!, uri: r.otpauth_uri! });
      else if (r.mfa_required) setStep({ kind: "mfa", token: r.mfa_token! });
      else await done();
    } catch (e) { setErr((e as ApiError).message); }
  };
  const verify = async (ev: React.FormEvent) => {
    ev.preventDefault(); if (!step) return; setBusy(true); setErr(null);
    try { await api.post(`${A}/auth/login/2fa`, { mfa_token: step.token, code }); await done(); }
    catch (e) { setErr((e as ApiError).message); if ((e as ApiError).code === "mfa_expired") setStep(null); } finally { setBusy(false); }
  };

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden bg-[#0d0f1f] px-4">
      <div className="pointer-events-none absolute inset-0 opacity-60" style={{ background: "radial-gradient(700px 360px at 15% 0%, rgba(99,102,241,.35), transparent), radial-gradient(600px 360px at 100% 100%, rgba(251,191,36,.18), transparent)" }} />
      <div className="absolute right-4 top-4"><ThemeToggle /></div>
      <div className="relative w-full max-w-[400px] rounded-2xl border border-border bg-surface p-7 shadow-lg">
        <div className="mb-6 flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-xl bg-amber-400 text-slate-900"><ShieldCheck className="size-5" /></span>
          <div><h1 className="text-lg font-semibold tracking-tight">Super Admin</h1><p className="text-xs text-fg-subtle">Restricted area · authorised staff only</p></div></div>
        {!step ? (
          <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
            <Field label="Admin email" error={errors.email?.message}><Input type="email" autoComplete="username" autoFocus {...register("email")} /></Field>
            <Field label="Password" error={errors.password?.message}>
              <div className="relative"><Input type={show ? "text" : "password"} autoComplete="current-password" className="pr-10" {...register("password")} />
                <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fg-subtle hover:text-fg">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div>
            </Field>
            {err && <p role="alert" className="flex items-center gap-2 text-sm text-danger"><AlertCircle className="size-4 shrink-0" />{err}</p>}
            <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>Sign in</Button>
          </form>
        ) : (
          <form onSubmit={verify} className="space-y-4">
            {step.kind === "setup" ? (
              <>
                <p className="text-sm text-fg-muted">Two-factor authentication is required. Scan this QR code in an authenticator app, then enter the 6-digit code.</p>
                <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-white p-3">{qr && /* eslint-disable-next-line @next/next/no-img-element */ <img src={qr} alt="Authenticator QR code" width={180} height={180} />}</div>
                <p className="break-all rounded-md bg-bg-subtle p-2 text-center font-mono text-xs text-fg-muted">{step.secret}</p>
              </>
            ) : <p className="text-sm text-fg-muted">Enter the 6-digit code from your authenticator app.</p>}
            <Field label="Authentication code"><Input inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" className="text-center text-lg tracking-[0.4em]" /></Field>
            {err && <p role="alert" className="flex items-center gap-2 text-sm text-danger"><AlertCircle className="size-4 shrink-0" />{err}</p>}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length < 6}>{step.kind === "setup" ? "Enable and sign in" : "Verify and sign in"}</Button>
            <button type="button" onClick={() => { setStep(null); setCode(""); setErr(null); }} className="mx-auto flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg"><ArrowLeft className="size-3.5" /> Back</button>
          </form>
        )}
      </div>
    </div>
  );
}
export const dynamic = "force-dynamic";
export default function Page() { return <Suspense><Form /></Suspense>; }
