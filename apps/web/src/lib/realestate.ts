import { BadgeCheck, BookmarkCheck, DoorOpen, Hourglass, Home, KeyRound, Tag } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { formatMoneyCompact } from "@crm/ui";

export type UnitStatus = "vacant" | "for_sale" | "for_rent" | "on_hold" | "booked" | "sold" | "rented" | "self_occupied";

/** One entry per colour on the building. `bg` is the lit window, `ink` the text on it. Every status also has its own icon
 *  so the meaning never depends on colour alone (red/green is a common colour-blindness pair). */
export const STATUS: Record<UnitStatus, { label: string; hint: string; bg: string; bgDark: string; ink: string; icon: LucideIcon; group: "open" | "progress" | "closed" | "lived" }> = {
  vacant: { label: "Vacant", hint: "Empty, not listed yet", bg: "#dfe5ee", bgDark: "#2b3140", ink: "#3b4558", icon: DoorOpen, group: "open" },
  for_sale: { label: "For sale", hint: "Listed for sale", bg: "#dc2626", bgDark: "#dc2626", ink: "#ffffff", icon: Tag, group: "open" },
  for_rent: { label: "For rent", hint: "Listed for rent", bg: "#0e7490", bgDark: "#0e7490", ink: "#ffffff", icon: KeyRound, group: "open" },
  on_hold: { label: "On hold", hint: "Held for a client", bg: "#7c3aed", bgDark: "#7c3aed", ink: "#ffffff", icon: Hourglass, group: "progress" },
  booked: { label: "Booked", hint: "Token paid", bg: "#2563eb", bgDark: "#2563eb", ink: "#ffffff", icon: BookmarkCheck, group: "progress" },
  sold: { label: "Sold", hint: "Sale completed", bg: "#334155", bgDark: "#475569", ink: "#ffffff", icon: BadgeCheck, group: "closed" },
  rented: { label: "Rented", hint: "Currently on rent", bg: "#15803d", bgDark: "#15803d", ink: "#ffffff", icon: KeyRound, group: "closed" },
  self_occupied: { label: "Self occupied", hint: "Lived in by the owner", bg: "#f59e0b", bgDark: "#f59e0b", ink: "#3a2100", icon: Home, group: "lived" },
};
export const STATUS_ORDER = Object.keys(STATUS) as UnitStatus[];
export const AVAILABLE: UnitStatus[] = ["vacant", "for_sale", "for_rent"];

export const BHK_OPTIONS = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "Studio", "Penthouse"];
export const FACINGS = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West"];
export const PROJECT_KINDS = [["residential", "Residential"], ["commercial", "Commercial"], ["villa", "Villas"], ["plotted", "Plots"], ["mixed", "Mixed use"]] as const;
export const PROJECT_STAGES = [["ready", "Ready to move"], ["under_construction", "Under construction"], ["upcoming", "Upcoming"]] as const;
export const UNIT_KINDS = [["apartment", "Flat"], ["villa", "Villa"], ["shop", "Shop"], ["office", "Office"], ["plot", "Plot"]] as const;

export type CountMap = Partial<Record<UnitStatus, number>>;
export type Summary = { counts: CountMap; total: number; available: number; closed: number; occupancy_pct: number; for_sale_value?: number; units_per_floor?: number; floors?: number };
export type TowerLite = { id: string; name: string; floors: number; has_ground: boolean; status: string; summary: Summary };
export type Project = {
  id: string; name: string; developer: string | null; kind: string; stage: string; city: string | null; locality: string | null; sector: string | null; address: string | null;
  rera_id: string | null; amenities: string[]; description: string | null; owner_id: string | null; tags: string[]; possession_date: string | null;
  summary: Summary; towers: TowerLite[]; starting_price: number | null; created_at: string;
};
export type UnitMini = { id: string; number: string; floor: number; position: number; status: UnitStatus; kind: string; bhk: string | null; area_sqft: number | null; facing: string | null; sale_price: number | null; monthly_rent: number | null; hold_until: string | null };
export type Building = {
  project: { id: string; name: string; city: string | null; locality: string | null; sector: string | null; developer: string | null; stage: string };
  tower: { id: string; name: string; floors: number; has_ground: boolean };
  floors: { floor: number; units: UnitMini[] }[];
  summary: Summary;
};
export type Person = { id: string; name: string; phone: string | null };
export type Unit = UnitMini & {
  name: string; project_id: string; tower_id: string; tower_name: string | null; project_name: string | null; project_city: string | null; floor_label: string; notes: string | null;
  owner_contact: Person | null; occupant_contact: Person | null; hold_lead: { id: string; name: string } | null; held_by_name: string | null; days_in_status: number | null;
  owner_contact_id: string | null; tags: string[]; match?: { score: number; reasons: string[] };
};
export type UnitEvent = { id: string; type: string; from_status: UnitStatus | null; to_status: UnitStatus | null; note: string | null; user_name: string | null; created_at: string };
export type MatchLead = { id: string; name: string; phone: string | null; intent: string | null; bhk: string | null; budget_min: number | null; budget_max: number | null; status: string; score: number; reasons: string[] };

export const floorLabel = (f: number) => (f === 0 ? "Ground" : `Floor ${String(f).padStart(2, "0")}`);
export const money = (v: number | null | undefined) => (v == null ? "—" : formatMoneyCompact(v));
/** What a flat costs, in the way a broker says it: the sale price, or rent per month. */
export const priceLine = (u: Pick<UnitMini, "status" | "sale_price" | "monthly_rent">) =>
  u.status === "for_rent" || u.status === "rented" ? (u.monthly_rent ? `${money(u.monthly_rent)}/mo` : "—") : u.sale_price ? money(u.sale_price) : u.monthly_rent ? `${money(u.monthly_rent)}/mo` : "—";
export const where = (p: { sector?: string | null; locality?: string | null; city?: string | null }) => [p.sector, p.locality, p.city].filter(Boolean).join(", ");
export const holdLeft = (iso: string | null) => {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3.6e6);
  return h >= 48 ? `${Math.floor(h / 24)}d left` : h >= 1 ? `${h}h left` : `${Math.max(1, Math.floor(ms / 6e4))}m left`;
};
