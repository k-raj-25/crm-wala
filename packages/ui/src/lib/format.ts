const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AUD: "A$", CAD: "C$", SGD: "S$", AED: "AED " };

/** Full currency amount, e.g. ₹18,50,000 (Indian grouping for INR). */
export function formatMoney(value: number | string | null | undefined, currency = "INR", opts: { decimals?: number } = {}) {
  const n = Number(value ?? 0);
  const locale = currency === "INR" ? "en-IN" : "en-US";
  return `${SYMBOLS[currency] ?? currency + " "}${n.toLocaleString(locale, { maximumFractionDigits: opts.decimals ?? 0, minimumFractionDigits: opts.decimals ?? 0 })}`;
}

/** Compact amount: ₹18.5L, ₹2.4Cr, $1.2M. */
export function formatMoneyCompact(value: number | string | null | undefined, currency = "INR") {
  const n = Number(value ?? 0);
  const sym = SYMBOLS[currency] ?? currency + " ";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  const trim = (x: number) => x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2).replace(/\.0+$|(\.\d*[1-9])0+$/, "$1");
  if (currency === "INR") {
    if (abs >= 1e7) return `${sign}${sym}${trim(abs / 1e7)}Cr`;
    if (abs >= 1e5) return `${sign}${sym}${trim(abs / 1e5)}L`;
    if (abs >= 1e3) return `${sign}${sym}${trim(abs / 1e3)}K`;
    return `${sign}${sym}${Math.round(abs)}`;
  }
  if (abs >= 1e9) return `${sign}${sym}${trim(abs / 1e9)}B`;
  if (abs >= 1e6) return `${sign}${sym}${trim(abs / 1e6)}M`;
  if (abs >= 1e3) return `${sign}${sym}${trim(abs / 1e3)}K`;
  return `${sign}${sym}${Math.round(abs)}`;
}

/** Minor units (paise/cents) → major, for billing amounts. */
export const fromMinor = (v: number | null | undefined) => (v ?? 0) / 100;

export function formatNumber(n: number | null | undefined) {
  return (n ?? 0).toLocaleString("en-IN");
}

export function formatPercent(n: number | null | undefined, digits = 1) {
  return `${(n ?? 0).toFixed(digits).replace(/\.0+$/, "")}%`;
}

export function initials(name: string | null | undefined) {
  if (!name) return "?";
  const parts = name.replace(/^(dr|mr|mrs|ms)\.?\s+/i, "").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

export function timeAgo(iso: string | Date | null | undefined, now = new Date()) {
  if (!iso) return "—";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const s = Math.round((now.getTime() - d.getTime()) / 1000);
  const future = s < 0;
  const a = Math.abs(s);
  const unit = a < 60 ? "just now" : a < 3600 ? `${Math.floor(a / 60)}m` : a < 86400 ? `${Math.floor(a / 3600)}h` : a < 86400 * 30 ? `${Math.floor(a / 86400)}d` : a < 86400 * 365 ? `${Math.floor(a / (86400 * 30))}mo` : `${Math.floor(a / (86400 * 365))}y`;
  if (unit === "just now") return unit;
  return future ? `in ${unit}` : `${unit} ago`;
}

export function formatDate(iso: string | Date | null | undefined, style: "short" | "long" | "datetime" | "time" = "short", timeZone?: string) {
  if (!iso) return "—";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const base = { timeZone } as const;
  if (style === "time") return d.toLocaleTimeString("en-IN", { ...base, hour: "numeric", minute: "2-digit" });
  if (style === "datetime") return d.toLocaleString("en-IN", { ...base, day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  if (style === "long") return d.toLocaleDateString("en-IN", { ...base, weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return d.toLocaleDateString("en-IN", { ...base, day: "numeric", month: "short", year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}

export function dayLabel(iso: string | Date) {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const today = new Date();
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(today) - start(d)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff > 1 && diff < 7) return d.toLocaleDateString("en-IN", { weekday: "long" });
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}

/** "2 days", "18 hours", "45 minutes" from seconds. */
export function humanDuration(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 86400) { const d = Math.floor(s / 86400); return `${d} day${d === 1 ? "" : "s"}`; }
  if (s >= 3600) { const h = Math.floor(s / 3600); return `${h} hour${h === 1 ? "" : "s"}`; }
  const m = Math.max(1, Math.floor(s / 60));
  return `${m} minute${m === 1 ? "" : "s"}`;
}
