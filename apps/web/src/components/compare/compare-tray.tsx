"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Building2, Scale, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { Button, Tooltip } from "@crm/ui";
import { navigate } from "@/components/shell/pending-nav";
import { MAX_COMPARE, compare, societyCompare, useCompare, useSocietyCompare } from "@/lib/compare";

/** Floats at the bottom of every page while flats or societies are picked, so the comparison is always one tap away. */
export function CompareTray() {
  const list = useCompare();
  const socs = useSocietyCompare();
  const path = usePathname();
  const router = useRouter();
  const show = (list.length > 0 || socs.length > 0) && !path.startsWith("/app/compare");
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const what = [list.length ? plural(list.length, "flat", "flats") : null, socs.length ? plural(socs.length, "society", "societies") : null].filter(Boolean).join(" · ");
  return (
    <AnimatePresence>
      {show && (
        <motion.div key="tray" initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }} transition={{ type: "spring", stiffness: 420, damping: 34 }}
          className="fixed inset-x-4 bottom-[calc(88px+env(safe-area-inset-bottom))] z-30 mx-auto max-w-md md:inset-x-auto md:bottom-6 md:left-1/2 md:mx-0 md:w-auto md:max-w-none md:-translate-x-1/2" role="region" aria-label="To compare">
          <div data-refract className="flex items-center gap-2 glass-pop rounded-full border border-border p-2 pl-4 shadow-lg">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"><Scale className="size-4" /></span>
            <div className="min-w-0 flex-1 md:flex-none">
              <p className="text-sm font-medium leading-tight">{what} <span className="text-fg-muted">to compare</span></p>
              <p className="truncate text-xs text-fg-subtle md:hidden">{[...list.map((f) => f.number), ...socs.map((s) => s.name)].join(", ")}</p>
            </div>
            <ul className="hidden max-w-[46vw] items-center gap-1 overflow-x-auto md:flex">
              <AnimatePresence initial={false}>
                {list.map((f) => (
                  <motion.li key={f.id} layout initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }}
                    className="flex shrink-0 items-center gap-1 rounded-full border border-border bg-surface-2 py-0.5 pl-2.5 pr-1 text-xs font-medium">
                    <Tooltip content={f.where || `Flat ${f.number}`}><span>{f.number}</span></Tooltip>
                    <button type="button" onClick={() => compare.remove(f.id)} aria-label={`Remove flat ${f.number}`} className="grid size-5 place-items-center rounded-full text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-3" /></button>
                  </motion.li>
                ))}
                {socs.map((s) => (
                  <motion.li key={s.id} layout initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }}
                    className="flex max-w-[160px] shrink-0 items-center gap-1 rounded-full border border-border bg-surface-2 py-0.5 pl-2 pr-1 text-xs font-medium">
                    <Building2 className="size-3 shrink-0 text-fg-subtle" /><Tooltip content={s.where || s.name}><span className="truncate">{s.name}</span></Tooltip>
                    <button type="button" onClick={() => societyCompare.remove(s.id)} aria-label={`Remove ${s.name}`} className="grid size-5 shrink-0 place-items-center rounded-full text-fg-subtle hover:bg-surface-hover hover:text-fg"><X className="size-3" /></button>
                  </motion.li>
                ))}
              </AnimatePresence>
              {list.length > 0 && !socs.length && list.length < MAX_COMPARE && <li className="shrink-0 px-1 text-xs text-fg-subtle">{MAX_COMPARE - list.length} more</li>}
            </ul>
            <Button size="sm" onClick={() => navigate(router, list.length ? "/app/compare" : "/app/compare?tab=societies")}>Compare <ArrowRight /></Button>
            <Tooltip content="Clear the list"><Button size="icon-sm" variant="ghost" onClick={() => { compare.clear(); societyCompare.clear(); }} aria-label="Clear the list"><X /></Button></Tooltip>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
