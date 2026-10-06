"use client";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { ApiError, Button, Dialog, DialogContent, DialogFooter, Field, Input } from "@crm/ui";
import { A, api } from "@/lib/api";

type Ctx = { run: <T>(fn: () => Promise<T>) => Promise<T> };
const StepCtx = React.createContext<Ctx | null>(null);

/** Sensitive actions need a TOTP code verified within the last hour. `run` retries the action once after the admin re-verifies. */
export function useStepUp() {
  const c = React.useContext(StepCtx);
  if (!c) throw new Error("useStepUp outside provider");
  return c.run;
}

export function StepUpProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = React.useState<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);
  const [code, setCode] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const run = React.useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    try { return await fn(); } catch (e) {
      if (!(e instanceof ApiError) || e.code !== "mfa_recent_required") throw e;
      await new Promise<void>((resolve, reject) => { setCode(""); setErr(null); setPending({ resolve, reject }); });
      return fn();
    }
  }, []);

  const verify = async (ev: React.FormEvent) => {
    ev.preventDefault(); setBusy(true); setErr(null);
    try { await api.post(`${A}/auth/reverify`, { code }); pending?.resolve(); setPending(null); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const cancel = () => { pending?.reject(new Error("Verification cancelled")); setPending(null); };

  return (
    <StepCtx.Provider value={{ run }}>
      {children}
      <Dialog open={!!pending} onOpenChange={(o) => !o && cancel()}>
        <DialogContent title="Confirm it's you" description="This action is sensitive. Enter a fresh code from your authenticator app." size="sm">
          <form onSubmit={verify} className="space-y-4">
            <div className="flex items-center gap-3 rounded-lg bg-primary-soft p-3 text-sm text-primary"><ShieldCheck className="size-5 shrink-0" />Verification lasts one hour.</div>
            <Field label="Authentication code" error={err ?? undefined}>
              <Input inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" className="text-center text-lg tracking-[0.4em]" />
            </Field>
            <DialogFooter><Button type="button" variant="secondary" onClick={cancel}>Cancel</Button><Button type="submit" loading={busy} disabled={code.length < 6}>Verify</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </StepCtx.Provider>
  );
}
