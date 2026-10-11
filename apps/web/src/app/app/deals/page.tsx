import { redirect } from "next/navigation";

/** Deals now live inside Pipeline (table mode). Old links and filters keep working. */
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) if (typeof v === "string") q.set(k, v);
  q.set("mode", "list");
  redirect(`/app/pipeline?${q.toString()}`);
}
