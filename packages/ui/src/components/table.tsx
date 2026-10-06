import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import * as React from "react";
import { cn } from "../lib/cn";

export const Table = ({ className, ...p }: React.TableHTMLAttributes<HTMLTableElement>) => <table className={cn("w-full border-collapse text-sm", className)} {...p} />;
export const THead = ({ className, ...p }: React.HTMLAttributes<HTMLTableSectionElement>) => <thead className={cn("sticky top-0 z-[1] bg-surface-2 text-left", className)} {...p} />;
export const TR = ({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) => <tr className={cn("border-b border-border transition-colors last:border-0", className)} {...p} />;
export const TD = ({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) => <td className={cn("px-4 py-3 align-middle", className)} {...p} />;
export function TH({ className, children, sortable, sortDir: dir, onSort, ...p }: React.ThHTMLAttributes<HTMLTableCellElement> & { sortable?: boolean; sortDir?: "asc" | "desc" | null; onSort?: () => void }) {
  return (
    <th className={cn("whitespace-nowrap border-b border-border px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-fg-subtle", className)} aria-sort={dir ? (dir === "asc" ? "ascending" : "descending") : undefined} {...p}>
      {sortable ? (
        <button onClick={onSort} className="group -mx-1 inline-flex items-center gap-1 rounded px-1 uppercase tracking-wide hover:text-fg">
          {children}
          {dir === "asc" ? <ArrowUp className="size-3 text-primary" /> : dir === "desc" ? <ArrowDown className="size-3 text-primary" /> : <ChevronsUpDown className="size-3 opacity-0 transition-opacity group-hover:opacity-60" />}
        </button>
      ) : children}
    </th>
  );
}
