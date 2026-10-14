import { PageSkeleton } from "@/components/shell/route-skeleton";

/** Fallback for any /app route without its own loading.tsx (e.g. entering Settings). */
export default function Loading() { return <PageSkeleton wide />; }
