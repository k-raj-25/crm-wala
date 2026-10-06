"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button, ErrorState, Spinner } from "@crm/ui";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
function Inner() {
  const code = useSearchParams().get("code");
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!code) { setFailed(true); return; }
    api.post("/api/v1/auth/impersonate/exchange", { code }).then(() => { window.location.href = "/app"; }).catch(() => setFailed(true));
  }, [code, router]);
  return failed
    ? <ErrorState kind="session_expired" title="Impersonation link expired" description="Start impersonation again from the admin console." action={<Button onClick={() => router.replace("/login")}>Go to sign in</Button>} />
    : <div className="flex min-h-dvh items-center justify-center"><Spinner className="size-8 text-primary" /></div>;
}
export default function Page() { return <Suspense><Inner /></Suspense>; }
