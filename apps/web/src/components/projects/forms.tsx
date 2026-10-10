"use client";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import * as React from "react";
import { ApiError, Button, Checkbox, Dialog, DialogContent, DialogFooter, Field, Input, NativeSelect, useToast } from "@crm/ui";
import { api } from "@/lib/api";
import { BHK_OPTIONS, PROJECT_KINDS, PROJECT_STAGES, UNIT_KINDS } from "@/lib/realestate";
import type { Project } from "@/lib/realestate";

const KIND_TO_UNIT: Record<string, string> = { residential: "apartment", commercial: "office", villa: "villa", plotted: "plot", mixed: "apartment" };

type TowerForm = { name: string; floors: number; per_floor: number; ground: boolean; kind: string; bhk: string; area: string; price: string };
const emptyTower = (name = "Tower A", kind = "apartment"): TowerForm => ({ name, floors: 10, per_floor: 4, ground: true, kind, bhk: kind === "apartment" ? "3 BHK" : "", area: "", price: "" });

/** The building you're about to create, drawn live as you change the numbers. */
export function GridPreview({ floors, perFloor, ground }: { floors: number; perFloor: number; ground: boolean }) {
  const rows = Math.min(floors + (ground ? 1 : 0), 16);
  const cols = Math.min(perFloor, 10);
  return (
    <div className="rounded-xl bg-bg-subtle p-4" aria-hidden>
      <div className="mx-auto flex w-full max-w-[260px] flex-col-reverse gap-[3px] rounded-md border border-border-strong bg-surface p-1.5">
        {Array.from({ length: rows }).map((_, r) => (
          <motion.div key={r} layout initial={{ opacity: 0, scaleY: 0.4 }} animate={{ opacity: 1, scaleY: 1 }} transition={{ delay: r * 0.02 }} className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
            {Array.from({ length: cols }).map((__, c) => <span key={c} className="h-3.5 rounded-[3px] bg-[#dfe5ee] dark:bg-[#2b3140]" />)}
          </motion.div>
        ))}
      </div>
      <p className="mt-3 text-center text-xs text-fg-muted">{floors + (ground ? 1 : 0)} floors × {perFloor} flats = <b className="text-fg">{(floors + (ground ? 1 : 0)) * perFloor} flats</b>{(rows < floors + (ground ? 1 : 0) || cols < perFloor) && " (preview trimmed)"}</p>
    </div>
  );
}

function TowerFields({ v, onChange, errors }: { v: TowerForm; onChange: (v: TowerForm) => void; errors?: Record<string, string> }) {
  const set = <K extends keyof TowerForm>(k: K, val: TowerForm[K]) => onChange({ ...v, [k]: val });
  const n = (s: string, k: "floors" | "per_floor", max: number, min: number) => set(k, Math.min(Math.max(Number(s) || 0, min), max));
  return (
    <div className="grid gap-5 sm:grid-cols-[1fr_240px]">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><Field label="Tower / block name" error={errors?.name} required><Input value={v.name} onChange={(e) => set("name", e.target.value)} maxLength={80} placeholder="Tower D-13" /></Field></div>
        <Field label="Floors above ground" hint="Not counting the ground floor"><Input type="number" min={0} max={120} value={v.floors} onChange={(e) => n(e.target.value, "floors", 120, 0)} /></Field>
        <Field label="Flats on each floor"><Input type="number" min={1} max={24} value={v.per_floor} onChange={(e) => n(e.target.value, "per_floor", 24, 1)} /></Field>
        <div className="col-span-2"><label className="flex cursor-pointer items-center gap-2.5 text-sm"><Checkbox checked={v.ground} onCheckedChange={(c) => set("ground", c)} /> The tower has flats on the ground floor</label></div>
        <Field label="Type of unit"><NativeSelect value={v.kind} onChange={(e) => set("kind", e.target.value)}>{UNIT_KINDS.map(([a, b]) => <option key={a} value={a}>{b}</option>)}</NativeSelect></Field>
        <Field label="Usual size"><NativeSelect value={v.bhk} onChange={(e) => set("bhk", e.target.value)}><option value="">Mixed / not sure</option>{BHK_OPTIONS.map((b) => <option key={b}>{b}</option>)}</NativeSelect></Field>
        <Field label="Usual area (sq ft)" hint="You can change each flat later"><Input type="number" min={0} value={v.area} onChange={(e) => set("area", e.target.value)} placeholder="1800" /></Field>
        <Field label="Usual price (₹)"><Input type="number" min={0} value={v.price} onChange={(e) => set("price", e.target.value)} placeholder="24000000" /></Field>
      </div>
      <GridPreview floors={v.floors} perFloor={v.per_floor} ground={v.ground} />
    </div>
  );
}

const towerBody = (v: TowerForm) => ({ name: v.name.trim(), floors: v.floors, units_per_floor: v.per_floor, has_ground: v.ground, kind: v.kind, bhk: v.bhk || undefined, area_sqft: v.area ? Number(v.area) : undefined, sale_price: v.price ? Number(v.price) : undefined });

export function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter(); const qc = useQueryClient(); const toast = useToast();
  const [step, setStep] = React.useState<1 | 2>(1);
  const [p, setP] = React.useState({ name: "", developer: "", city: "", sector: "", locality: "", kind: "residential", stage: "ready" });
  const [t, setT] = React.useState<TowerForm>(emptyTower());
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<Record<string, string>>({});
  React.useEffect(() => { if (open) { setStep(1); setErr({}); } }, [open]);
  const kindChange = (kind: string) => { setP({ ...p, kind }); setT({ ...t, kind: KIND_TO_UNIT[kind] ?? "apartment", bhk: KIND_TO_UNIT[kind] === "apartment" ? t.bhk || "3 BHK" : "" }); };

  const create = async (withTower: boolean) => {
    setBusy(true);
    try {
      const proj = await api.post<Project>("/api/v1/projects", { name: p.name.trim(), developer: p.developer || undefined, city: p.city || undefined, sector: p.sector || undefined, locality: p.locality || undefined, kind: p.kind, stage: p.stage });
      let tid: string | undefined;
      if (withTower) tid = (await api.post<{ id: string }>(`/api/v1/projects/${proj.id}/towers`, towerBody(t))).id;
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(withTower ? `${proj.name} is ready — ${t.name} has been built` : `${proj.name} created`);
      onOpenChange(false);
      router.push(`/app/projects/${proj.id}${tid ? `?tower=${tid}` : ""}`);
    } catch (e) {
      if (e instanceof ApiError) { setErr(Object.fromEntries(Object.entries((e.details ?? {}) as Record<string, string>))); toast.error(e.message); } else toast.error("Something went wrong. Please try again.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title={step === 1 ? "New project" : "Build the first tower"} description={step === 1 ? "Where is it, and who is building it?" : "Tell us how tall it is. We'll draw every flat for you — you can fine-tune them afterwards."}>
        {step === 1 ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2"><Field label="Project name" required error={err.name}><Input autoFocus value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} placeholder="Ireo Victory Valley" maxLength={160} /></Field></div>
              <Field label="Builder / developer"><Input value={p.developer} onChange={(e) => setP({ ...p, developer: e.target.value })} placeholder="Ireo" /></Field>
              <Field label="City"><Input value={p.city} onChange={(e) => setP({ ...p, city: e.target.value })} placeholder="Gurgaon" /></Field>
              <Field label="Sector / area"><Input value={p.sector} onChange={(e) => setP({ ...p, sector: e.target.value })} placeholder="Sector 67" /></Field>
              <Field label="Road / locality"><Input value={p.locality} onChange={(e) => setP({ ...p, locality: e.target.value })} placeholder="Golf Course Ext. Road" /></Field>
              <Field label="Kind"><NativeSelect value={p.kind} onChange={(e) => kindChange(e.target.value)}>{PROJECT_KINDS.map(([a, b]) => <option key={a} value={a}>{b}</option>)}</NativeSelect></Field>
              <Field label="Status"><NativeSelect value={p.stage} onChange={(e) => setP({ ...p, stage: e.target.value })}>{PROJECT_STAGES.map(([a, b]) => <option key={a} value={a}>{b}</option>)}</NativeSelect></Field>
            </div>
            <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="secondary" loading={busy} disabled={!p.name.trim()} onClick={() => create(false)}>Create without towers</Button><Button disabled={!p.name.trim()} onClick={() => setStep(2)}>Next: build a tower</Button></DialogFooter>
          </>
        ) : (
          <>
            <TowerFields v={t} onChange={setT} errors={err} />
            <DialogFooter><Button variant="ghost" onClick={() => setStep(1)}>Back</Button><Button loading={busy} disabled={!t.name.trim()} onClick={() => create(true)}>Create project &amp; tower</Button></DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function AddTowerDialog({ open, onOpenChange, projectId, projectKind, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; projectId: string; projectKind?: string; onCreated: (towerId: string) => void }) {
  const qc = useQueryClient(); const toast = useToast();
  const [t, setT] = React.useState<TowerForm>(emptyTower("Tower B", KIND_TO_UNIT[projectKind ?? "residential"]));
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<Record<string, string>>({});
  const save = async () => {
    setBusy(true); setErr({});
    try {
      const r = await api.post<{ id: string }>(`/api/v1/projects/${projectId}/towers`, towerBody(t));
      ["project", "projects", "building"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success(`${t.name} built`); onOpenChange(false); onCreated(r.id);
    } catch (e) { if (e instanceof ApiError) { setErr({ name: e.status === 409 ? e.message : "" }); toast.error(e.message); } } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" title="Add a tower" description="We'll create every flat on every floor. You can edit them one by one afterwards.">
        <TowerFields v={t} onChange={setT} errors={err} />
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={!t.name.trim()} onClick={save}>Build tower</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AddFloorsDialog({ open, onOpenChange, projectId, towerId, perFloor }: { open: boolean; onOpenChange: (o: boolean) => void; projectId: string; towerId: string; perFloor: number }) {
  const qc = useQueryClient(); const toast = useToast();
  const [count, setCount] = React.useState(1); const [per, setPer] = React.useState(perFloor);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (open) setPer(perFloor || 4); }, [open, perFloor]);
  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/api/v1/projects/${projectId}/towers/${towerId}/floors`, { count, units_per_floor: per });
      ["project", "projects", "building"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success(`${count} floor${count > 1 ? "s" : ""} added on top`); onOpenChange(false);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Couldn't add floors"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm" title="Add floors" description="New floors are built on top and copy the size and price of the current top floor.">
        <div className="grid grid-cols-2 gap-3">
          <Field label="How many floors?"><Input type="number" min={1} max={20} value={count} onChange={(e) => setCount(Math.min(Math.max(Number(e.target.value) || 1, 1), 20))} /></Field>
          <Field label="Flats on each floor"><Input type="number" min={1} max={24} value={per} onChange={(e) => setPer(Math.min(Math.max(Number(e.target.value) || 1, 1), 24))} /></Field>
        </div>
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} onClick={save}>Add floors</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AddUnitDialog({ open, onOpenChange, towerId, floors, hasGround, defaultFloor }: { open: boolean; onOpenChange: (o: boolean) => void; towerId: string; floors: number; hasGround: boolean; defaultFloor?: number }) {
  const qc = useQueryClient(); const toast = useToast();
  const [f, setF] = React.useState({ floor: defaultFloor ?? 1, number: "", bhk: "", area: "", price: "" });
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string>("");
  React.useEffect(() => { if (open) { setErr(""); setF((x) => ({ ...x, number: "", floor: defaultFloor ?? x.floor })); } }, [open, defaultFloor]);
  const save = async () => {
    setBusy(true); setErr("");
    try {
      await api.post("/api/v1/units", { tower_id: towerId, floor: f.floor, number: f.number.trim(), bhk: f.bhk || undefined, area_sqft: f.area ? Number(f.area) : undefined, sale_price: f.price ? Number(f.price) : undefined });
      ["building", "project", "projects"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success(`Unit ${f.number} added`); onOpenChange(false);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Couldn't add the unit"); } finally { setBusy(false); }
  };
  const floorOptions = Array.from({ length: floors + (hasGround ? 1 : 0) }, (_, i) => (hasGround ? i : i + 1));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" title="Add a flat" description="For a flat that isn't part of the regular layout, like a penthouse or a shop.">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Floor"><NativeSelect value={f.floor} onChange={(e) => setF({ ...f, floor: Number(e.target.value) })}>{floorOptions.map((n) => <option key={n} value={n}>{n === 0 ? "Ground floor" : `Floor ${n}`}</option>)}</NativeSelect></Field>
          <Field label="Flat number" required error={err}><Input autoFocus value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} placeholder="1005" maxLength={20} /></Field>
          <Field label="Size"><NativeSelect value={f.bhk} onChange={(e) => setF({ ...f, bhk: e.target.value })}><option value="">—</option>{BHK_OPTIONS.map((b) => <option key={b}>{b}</option>)}</NativeSelect></Field>
          <Field label="Area (sq ft)"><Input type="number" min={0} value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })} /></Field>
          <div className="col-span-2"><Field label="Price (₹)"><Input type="number" min={0} value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field></div>
        </div>
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={!f.number.trim()} onClick={save}>Add flat</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

