"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Field, Input } from "@crm/ui";
import { AuthShell } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";

const schema = z.object({ email: z.string().email("Enter a valid email") });
export default function ForgotPage() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const [sent, setSent] = useState<{ dev?: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (sent) return (
    <AuthShell title="Check your email" subtitle="If an account exists for that address, we've sent a link to reset your password. It expires in 1 hour.">
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary"><MailCheck className="size-7" /></div>
      {sent.dev && <p className="mb-4 rounded-lg border border-dashed border-border-strong p-3 text-xs text-fg-muted">Development mode: <Link className="font-medium text-primary underline" href={`/reset-password?token=${sent.dev}`}>open reset link</Link></p>}
      <Button asChild variant="secondary" size="lg" className="w-full"><Link href="/login">Back to sign in</Link></Button>
    </AuthShell>
  );
  return (
    <AuthShell title="Forgot your password?" subtitle="Enter your email and we'll send you a reset link." footer={<Link href="/login" className="font-medium text-primary hover:underline">Back to sign in</Link>}>
      <form onSubmit={handleSubmit(async (v) => { setError(null); try { const r = await api.post<{ dev_reset_token?: string | null }>("/api/v1/auth/forgot-password", v); setSent({ dev: r.dev_reset_token }); } catch (e) { setError((e as Error).message); } })} className="space-y-4" noValidate>
        <Field label="Work email" error={errors.email?.message}><Input type="email" autoFocus autoComplete="email" {...register("email")} /></Field>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>Send reset link</Button>
      </form>
    </AuthShell>
  );
}
