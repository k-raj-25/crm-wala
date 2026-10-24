import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SocietyPage } from "@/components/society/society-page";
import type { SocietyPageData } from "@/components/society/society-page";

// Same API the /api rewrite in next.config points at: a full URL, or a bare host:port from Render's private network.
const RAW_API = process.env.API_URL ?? "http://localhost:5000";
const API = /^https?:\/\//.test(RAW_API) ? RAW_API : `http://${RAW_API}`;

type Props = { params: Promise<{ token: string }> };

async function load(token: string): Promise<SocietyPageData | null> {
  if (!/^[\w-]{20,120}$/.test(token)) return null;
  const res = await fetch(`${API}/api/v1/public/societies/${token}`, { cache: "no-store" }).catch(() => null);
  if (!res) throw new Error("The society page is unavailable right now");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("The society page is unavailable right now");
  return (await res.json()).data as SocietyPageData;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const d = await load((await params).token).catch(() => null);
  if (!d) return { title: "Society details", robots: { index: false, follow: false } };
  const s = d.society;
  const bits = [s.location, s.starting_price && `from ${s.starting_price}`, s.stage].filter(Boolean).join(" · ");
  const title = d.company?.name ? `${s.name} · ${d.company.name}` : s.name;
  const image = d.photos[0]?.url;
  // the WhatsApp preview card: society name, a line of facts and the first photo
  return {
    title: { absolute: title },
    description: bits || `Photos, layouts, floor plans and brochure of ${s.name}`,
    robots: { index: false, follow: false },
    openGraph: { title: s.name, description: bits || undefined, type: "website", images: image ? [{ url: image }] : undefined },
  };
}

export default async function Page({ params }: Props) {
  const { token } = await params;
  const data = await load(token);
  if (!data) notFound();
  return <SocietyPage data={data} token={token} />;
}
