"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button, Field, useToast } from "@crm/ui";
import { AuthShell, PasswordInput, StrengthMeter } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
const schema = z.object({ password: z.string().min(10, "At least 10 characters").regex(/[A-Za-z]/, "Include letters").regex(/\d/, "Include a number"), confirm: z.string() }).refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });

function Inner() {
  const sp = useSearchParams(); const router = useRouter(); const toast = useToast();
  const token = sp.get("token") ?? "";
  const { register, handleSubmit, control, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const pw = useWatch({ control, name: "password" }) ?? "";
  const [error, setError] = useState<string | null>(null);
  if (!token) return <AuthShell title="Link missing" subtitle="Open the reset link from your email, or request a new one."><Button asChild size="lg" className="w-full"><Link href="/forgot-password">Request a new link</Link></Button></AuthShell>;
  return (
    <AuthShell title="Choose a new password" subtitle="You'll be signed out of all other devices.">
      <form onSubmit={handleSubmit(async (v) => { setError(null); try { await api.post("/api/v1/auth/reset-password", { token, password: v.password }); toast.success("Password updated", "Sign in with your new password."); router.replace("/login"); } catch (e) { setError((e as Error).message); } })} className="space-y-4" noValidate>
        <div><Field label="New password" error={errors.password?.message}><PasswordInput autoComplete="new-password" autoFocus {...register("password")} /></Field><StrengthMeter value={pw} /></div>
        <Field label="Confirm password" error={errors.confirm?.message}><PasswordInput autoComplete="new-password" {...register("confirm")} /></Field>
        {error && <p role="alert" className="text-sm text-danger">{error} <Link href="/forgot-password" className="underline">Request a new link</Link></p>}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>Update password</Button>
      </form>
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
