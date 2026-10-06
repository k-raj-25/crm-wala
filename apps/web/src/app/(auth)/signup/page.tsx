"use client";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button, Field, Input, NativeSelect } from "@crm/ui";
import { AuthShell, GoogleButton, OrDivider, PasswordInput, StrengthMeter } from "@/components/auth/auth-shell";
import { api } from "@/lib/api";
import { COMPANY_SIZES, INDUSTRIES, ROLES_TITLES } from "@/lib/constants";
import { applyApiErrors } from "@/lib/forms";
import { keys } from "@/lib/queries";
import type { Me } from "@/lib/types";

const schema = z.object({
  name: z.string().min(1, "Enter your name"), email: z.string().email("Enter a valid email"),
  password: z.string().min(10, "At least 10 characters").regex(/[A-Za-z]/, "Include letters").regex(/\d/, "Include a number"),
  company_name: z.string().min(1, "Enter your company name"), company_size: z.string().min(1, "Choose a size"), industry: z.string().min(1, "Choose an industry"), role: z.string().min(1, "Choose your role"),
});
type V = z.infer<typeof schema>;

export default function SignupPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api.get<{ google_enabled: boolean; require_email_verification: boolean; trial_days: number; signups_enabled: boolean }>("/api/v1/auth/config"), staleTime: Infinity });
  const { register, handleSubmit, setError, control, formState: { errors, isSubmitting } } = useForm<V>({ resolver: zodResolver(schema), defaultValues: { company_size: "", industry: "", role: "" } });
  const pw = useWatch({ control, name: "password" }) ?? "";
  const [formError, setFormError] = useState<string | null>(null);
  const days = cfg.data?.trial_days ?? 3;

  const onSubmit = async (v: V) => {
    setFormError(null);
    try {
      const me = await api.post<Me & { dev_verify_token?: string | null }>("/api/v1/auth/signup", v);
      qc.setQueryData(keys.me, me);
      if (me.dev_verify_token) sessionStorage.setItem("dev_verify_token", me.dev_verify_token);
      router.replace(cfg.data?.require_email_verification ? "/verify-email" : "/onboarding");
    } catch (e) { setFormError(applyApiErrors(e, setError, Object.keys(schema.shape))); }
  };

  return (
    <AuthShell wide title={`Start your ${days}-day free trial`} subtitle="No credit card. No long-term commitment. Set up in under 2 minutes." footer={<>Already have an account? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link></>}>
      {cfg.data && !cfg.data.signups_enabled && <div role="alert" className="mb-5 rounded-lg bg-warning-soft px-3.5 py-2.5 text-sm text-warning">New signups are temporarily paused. Please check back soon.</div>}
      {cfg.data?.google_enabled && <><GoogleButton label="Sign up with Google" /><OrDivider /></>}
      <form onSubmit={handleSubmit(onSubmit)} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Field label="Your name" error={errors.name?.message} className="sm:col-span-1"><Input autoComplete="name" autoFocus {...register("name")} /></Field>
        <Field label="Work email" error={errors.email?.message}><Input type="email" autoComplete="email" {...register("email")} /></Field>
        <div className="sm:col-span-2"><Field label="Password" error={errors.password?.message}><PasswordInput autoComplete="new-password" {...register("password")} /></Field><StrengthMeter value={pw} /></div>
        <Field label="Company name" error={errors.company_name?.message}><Input autoComplete="organization" {...register("company_name")} /></Field>
        <Field label="Company size" error={errors.company_size?.message}><NativeSelect {...register("company_size")}><option value="">Select…</option>{COMPANY_SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
        <Field label="Industry" error={errors.industry?.message}><NativeSelect {...register("industry")}><option value="">Select…</option>{INDUSTRIES.map((i) => <option key={i}>{i}</option>)}</NativeSelect></Field>
        <Field label="Your role" error={errors.role?.message}><NativeSelect {...register("role")}><option value="">Select…</option>{ROLES_TITLES.map((i) => <option key={i}>{i}</option>)}</NativeSelect></Field>
        {formError && <p role="alert" className="flex items-center gap-2 text-sm text-danger sm:col-span-2"><AlertCircle className="size-4 shrink-0" />{formError}</p>}
        <div className="sm:col-span-2">
          <Button type="submit" size="lg" className="w-full" loading={isSubmitting} disabled={cfg.data?.signups_enabled === false}>Create workspace & start trial</Button>
          <ul className="mt-4 grid gap-1.5 text-[13px] text-fg-muted sm:grid-cols-2">{[`${days} days of full access`, "Cancel or upgrade any time", "Import your data in minutes", "Your data is never deleted"].map((t) => <li key={t} className="flex items-center gap-2"><Check className="size-3.5 text-success" />{t}</li>)}</ul>
        </div>
      </form>
    </AuthShell>
  );
}
