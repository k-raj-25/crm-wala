"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, Lock, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Badge, Button, Card, ErrorState, Field, Input, Logo, Skeleton, formatMoney, fromMinor } from "@crm/ui";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";

function Inner() {
  const sid = useSearchParams().get("session") ?? ""; const router = useRouter(); const qc = useQueryClient();
  const q = useQuery({ queryKey: ["checkout", sid], enabled: !!sid, retry: false, queryFn: () => api.get<{ status: string; provider: string; quote: { plan_name: string; interval: string; currency: string; subtotal: number; discount: number; proration_credit: number; account_credit: number; tax: number; tax_name: string; total: number } }>(`/api/v1/billing/checkout/${sid}`) });
  const [busy, setBusy] = useState<"ok" | "fail" | null>(null); const [err, setErr] = useState<string | null>(null); const [done, setDone] = useState(false);
  const pay = async (outcome: "success" | "failure") => { setBusy(outcome === "success" ? "ok" : "fail"); setErr(null); try { await api.post("/api/v1/billing/mock/complete", { session_id: sid, outcome, card_last4: "4242" }); qc.invalidateQueries(); qc.invalidateQueries({ queryKey: keys.me }); setDone(true); setTimeout(() => router.replace("/app/billing"), 1800); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); } };
  if (q.isError) return <ErrorState kind="payment_failed" title="Checkout session not found" description="It may have expired or already been completed." action={<Button onClick={() => router.replace("/app/billing")}>Back to billing</Button>} />;
  if (done) return <div className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center text-center"><span className="mb-5 flex size-16 items-center justify-center rounded-full bg-success-soft text-success"><CheckCircle2 className="size-8" /></span><h1 className="text-2xl font-semibold">Payment successful</h1><p className="mt-2 text-fg-muted">Your subscription is active. Taking you back…</p></div>;
  const qt = q.data?.quote;
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between"><Logo /><Badge tone="warning"><Lock className="size-3" /> Test checkout — no real card is collected</Badge></div>
      <div className="grid gap-6 md:grid-cols-[1fr_380px]">
        <Card className="p-6"><h1 className="text-xl font-semibold">Payment details</h1><p className="mb-6 mt-1 text-sm text-fg-muted">This simulates a provider-hosted page. In production (Stripe/Razorpay) card entry happens on their domain and never reaches CRM Wala.</p>
          <div className="space-y-4"><Field label="Card number"><Input icon={<CreditCard />} defaultValue="4242 4242 4242 4242" inputMode="numeric" autoComplete="off" /></Field><div className="grid grid-cols-2 gap-4"><Field label="Expiry"><Input defaultValue="12 / 34" autoComplete="off" /></Field><Field label="CVC"><Input defaultValue="123" autoComplete="off" /></Field></div>
            {err && <p role="alert" className="rounded-lg bg-danger-soft p-3 text-sm text-danger">{err}</p>}
            <Button size="lg" className="w-full" onClick={() => pay("success")} loading={busy === "ok"} disabled={!qt}>Pay {qt ? formatMoney(fromMinor(qt.total), qt.currency, { decimals: 2 }) : ""}</Button>
            <button className="mx-auto block text-xs text-fg-subtle hover:text-danger" onClick={() => pay("failure")} disabled={!!busy}>Simulate a declined card</button></div></Card>
        <Card className="h-fit p-6"><h2 className="font-semibold">Order summary</h2>{!qt ? <Skeleton className="mt-4 h-32" /> : (
          <dl className="mt-4 space-y-2.5 text-sm"><div className="flex justify-between"><dt className="text-fg-muted">{qt.plan_name} ({qt.interval})</dt><dd className="tabular">{formatMoney(fromMinor(qt.subtotal), qt.currency, { decimals: 2 })}</dd></div>
            {qt.discount > 0 && <div className="flex justify-between text-success"><dt>Discount</dt><dd className="tabular">−{formatMoney(fromMinor(qt.discount), qt.currency, { decimals: 2 })}</dd></div>}{qt.proration_credit > 0 && <div className="flex justify-between text-success"><dt>Proration credit</dt><dd className="tabular">−{formatMoney(fromMinor(qt.proration_credit), qt.currency, { decimals: 2 })}</dd></div>}
            <div className="flex justify-between"><dt className="text-fg-muted">{qt.tax_name}</dt><dd className="tabular">{formatMoney(fromMinor(qt.tax), qt.currency, { decimals: 2 })}</dd></div><div className="flex justify-between border-t border-border pt-3 text-base font-semibold"><dt>Total</dt><dd className="tabular">{formatMoney(fromMinor(qt.total), qt.currency, { decimals: 2 })}</dd></div></dl>)}
          <p className="mt-5 flex items-center gap-2 text-xs text-fg-subtle"><ShieldCheck className="size-4" /> Cancel any time from Billing.</p></Card>
      </div>
    </div>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
