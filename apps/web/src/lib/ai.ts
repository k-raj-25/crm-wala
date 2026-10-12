"use client";
import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { api } from "./api";
import { useAccess } from "./queries";

/** One field the assistant wants to change. `to` is what gets sent; people can edit it before approving. */
export type AiChange = { key: string; label: string; from: unknown; to: unknown; input: "text" | "number" | "money" | "select" | "datetime" | "date" | "textarea" | "tags" | "readonly"; options?: { value: string; label: string }[] | null; display_from?: unknown; display_to?: unknown };
export type AiOp = { method: "POST" | "PATCH" | "PUT" | "DELETE"; path: string; body?: unknown };
export type AiProposal = {
  id: string; kind: string; title: string; description?: string | null; record?: { type: string; id: string; name: string; url?: string } | null; changes: AiChange[]; ops: AiOp[]; undo?: AiOp[] | null;
  items?: { id: string; name: string; url?: string; hint?: string }[] | null; warning?: string | null; url?: string | null; open_result?: string; duplicates?: { id: string; name: string; type: string; url: string; match?: string }[];
};
export type AiChart = { type?: "bar" | "line" | "donut"; title?: string; data: Record<string, unknown>[]; x: string; series: { key: string; label: string }[]; format?: string | null };
export type AiStatus = { mode: "workspace" | "platform" | "basic"; provider: string; provider_label: string; model: string | null; features: Record<string, boolean>; audio_files: boolean; photos: boolean; can_manage: boolean };

export function useAiStatus() {
  const { has, can } = useAccess();
  return useQuery({ queryKey: ["ai-status"], enabled: has("ai_assistant") && can("ai.use"), staleTime: 60_000, queryFn: () => api.get<AiStatus>("/api/v1/ai/status") });
}

/** True when the plan, the role and the workspace's AI settings all allow `feature`. */
export function useAiFeature(feature: string) {
  const { has, can } = useAccess(); const s = useAiStatus();
  return has("ai_assistant") && can("ai.use") && !!s.data && s.data.features[feature] !== false;
}

const PH = /^\{\{([\w.]+)\}\}$/;
type Results = Record<string, unknown>[];
function fill(v: unknown, values: Record<string, unknown>, results: Results): unknown {
  if (typeof v === "string") {
    const m = v.match(PH);
    if (m) { const k = m[1]; if (k.startsWith("result.")) { const [, i, f] = k.split("."); return results[Number(i)]?.[f]; } return values[k]; }
    return v.replace(/\{\{result\.(\d+)\.(\w+)\}\}/g, (_, i, f) => String(results[Number(i)]?.[f] ?? ""));
  }
  if (Array.isArray(v)) return v.map((x) => fill(x, values, results));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, fill(x, values, results)]));
  return v;
}
export const fillText = (s: string, results: Results) => fill(s, {}, results) as string;

/** Only our own API, never a full URL or a path that climbs out of /api/v1. */
const safePath = (p: string) => p.startsWith("/api/v1/") && !p.includes("..") && !p.includes("//");
const withVia = (p: string) => p + (p.includes("?") ? "&" : "?") + "via=ai";

async function call(op: AiOp, body: unknown) {
  if (!safePath(op.path)) throw new Error("The assistant prepared a change this app can't make.");
  const path = withVia(op.path);
  switch (op.method) {
    case "POST": return api.post<Record<string, unknown>>(path, body);
    case "PATCH": return api.patch<Record<string, unknown>>(path, body);
    case "PUT": return api.put<Record<string, unknown>>(path, body);
    case "DELETE": await api.delete(path); return {};
  }
}

/** Runs the proposal's calls in order as the signed-in user. Later calls can use earlier results ({{result.0.id}}). */
export async function runProposal(p: AiProposal, edits: Record<string, unknown> = {}) {
  const values: Record<string, unknown> = { ...Object.fromEntries(p.changes.map((c) => [c.key, c.to])), ...edits };
  const results: Results = [];
  for (const op of p.ops) { const r = await call({ ...op, path: fill(op.path, values, results) as string }, fill(op.body, values, results)); results.push((r ?? {}) as Record<string, unknown>); }
  return results;
}
export async function runUndo(p: AiProposal, results: Results) {
  for (const op of p.undo ?? []) await call({ ...op, path: fill(op.path, {}, results) as string }, fill(op.body, {}, results));
}
export const reportOutcome = (p: AiProposal, outcome: "approved" | "cancelled" | "undone" | "failed", error?: string) =>
  api.post("/api/v1/ai/proposals/outcome", { kind: p.kind, title: p.title.slice(0, 300), outcome, calls: p.ops.length, error: error?.slice(0, 300) }).catch(() => undefined);

export const waLink = (phone?: string | null, text?: string) => {
  const d = (phone ?? "").replace(/\D/g, ""); const n = d.length === 10 ? "91" + d : d;
  return `https://wa.me/${n}${text ? `?text=${encodeURIComponent(text)}` : ""}`;
};

export async function fileToImage(file: File): Promise<{ media_type: string; data: string }> {
  if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) throw new Error("Use a PNG, JPG or WebP photo.");
  if (file.size > 5_000_000) throw new Error("Photos up to 5 MB, please.");
  const buf = new Uint8Array(await file.arrayBuffer()); let s = "";
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return { media_type: file.type, data: btoa(s) };
}

type SR = { lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void; onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null };

/** Browser dictation (Chrome, Edge, Safari). Final phrases are passed to onText as they're recognised. */
export function useDictation(onText: (t: string) => void) {
  const [on, setOn] = React.useState(false); const [error, setError] = React.useState<string | null>(null); const rec = React.useRef<SR | null>(null);
  const cb = React.useRef(onText); cb.current = onText;
  const supported = typeof window !== "undefined" && !!((window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition);
  const start = (lang = "en-IN") => {
    const W = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR }; const C = W.SpeechRecognition ?? W.webkitSpeechRecognition;
    if (!C) { setError("Voice typing isn't available in this browser. Try Chrome, or upload a voice note."); return; }
    const r = new C(); r.lang = lang; r.continuous = true; r.interimResults = false;
    r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) cb.current(e.results[i][0].transcript.trim()); };
    r.onend = () => setOn(false); r.onerror = (e) => { setError(e.error === "not-allowed" ? "Allow microphone access to dictate." : "Couldn't hear that. Try again."); setOn(false); };
    rec.current = r; setError(null); r.start(); setOn(true);
  };
  const stop = () => { rec.current?.stop(); setOn(false); };
  React.useEffect(() => () => rec.current?.stop(), []);
  return { on, start, stop, supported, error };
}

export const MODE_LABEL: Record<AiStatus["mode"], string> = { workspace: "Your AI key", platform: "CRM Wala AI", basic: "Basic mode" };
