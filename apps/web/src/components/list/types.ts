import type * as React from "react";

export type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
export type Column = { key: string; label: string; sort?: string; render: (r: Row, ctx: { update: (id: string, patch: Record<string, unknown>) => void; canEdit: boolean }) => React.ReactNode; defaultVisible?: boolean; className?: string; align?: "right" };
export type FilterDef =
  | { kind: "multi"; param: string; label: string; options?: { value: string; label: string }[]; from?: "members" | "tags" | "statuses" | "sources" | "stages" }
  | { kind: "range"; param: string; label: string; unit?: string }
  | { kind: "date"; param: string; label: string }
  | { kind: "select"; param: string; label: string; options: { value: string; label: string }[] };
export type DefaultView = { id: string; name: string; params: Record<string, string> };
export type BulkAction = "assign" | "tags" | "delete" | "status" | "priority";
export type EntityConfig = {
  key: "leads" | "contacts" | "companies" | "deals";
  title: string; singular: string; entityType: "lead" | "contact" | "company" | "deal"; endpoint: string; perm: string; createKind: "lead" | "contact" | "company" | "deal";
  columns: Column[]; filters: FilterDef[]; defaultViews: DefaultView[]; defaultSort: string; bulk: BulkAction[]; href: (r: Row) => string;
  empty: { title: string; description: string }; importAs: "leads" | "contacts" | "companies" | "deals"; searchPlaceholder: string; mobile: (r: Row) => { title: React.ReactNode; subtitle?: React.ReactNode; meta?: React.ReactNode };
};
