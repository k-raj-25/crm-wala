import type { Metadata } from "next";
import { RecapPage } from "@/components/recap/recap-page";

// The page a buyer opens from WhatsApp after a site visit. Public, read-only, never indexed.
const RAW_API = process.env.API_URL ?? "http://localhost:5000";
const API = /^https?:\/\//.test(RAW_API) ? RAW_API : `http://${RAW_API}`;

type Props = { params: Promise<{ token: string }>; searchParams: Promise<{ preview?: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { token } = await params;
  const base: Metadata = { robots: { index: false, follow: false }, referrer: "no-referrer" };
  try {
    // ?meta=1: WhatsApp's link preview fetching this page doesn't count as the buyer opening it
    const r = await fetch(`${API}/api/v1/public/recaps/${encodeURIComponent(token)}?meta=1`, { cache: "no-store" });
    if (!r.ok) return { ...base, title: "Visit recap" };
    const d = (await r.json()).data;
    const title = d.project ? `Your visit to ${d.project.name}` : "Your site visit";
    const n = d.flats.length;
    const description = `${n ? `${n} flat${n === 1 ? "" : "s"} with prices` : "Prices"}${d.photos.length ? ", photos" : ""} and a side-by-side comparison${d.workspace ? ` from ${d.workspace}` : ""}.`;
    return { ...base, title: { absolute: title }, description, openGraph: { title, description, type: "website" } };
  } catch {
    return { ...base, title: "Visit recap" };
  }
}

export default async function Page({ params, searchParams }: Props) {
  const { token } = await params;
  const { preview } = await searchParams;
  return <RecapPage token={token} preview={preview === "1"} />;
}
