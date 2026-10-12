"use client";
import { Skeleton, SkeletonRows } from "@crm/ui";
import { PageContainer } from "./page";

/**
 * Instant placeholders, shown by the shell the moment a link is clicked (see pending-nav.tsx) and by the route
 * `loading.tsx` files while the page streams in. Shapes mirror each page's own data-loading state so nothing jumps
 * when the real page takes over.
 */
function Header({ actions = 2 }: { actions?: number }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="space-y-2"><Skeleton className="h-8 w-56" /><Skeleton className="h-4 w-80 max-w-full" /></div>
      {actions > 0 && <div className="flex gap-2">{Array.from({ length: actions }).map((_, i) => <Skeleton key={i} className="h-9 w-28 rounded-lg" />)}</div>}
    </div>
  );
}

const Status = ({ children }: { children: React.ReactNode }) => <div role="status" aria-label="Loading" aria-busy>{children}</div>;

export function DashboardSkeleton() {
  return (
    <Status><PageContainer wide>
      <Header actions={3} />
      <Skeleton className="h-40 rounded-2xl" />
      <div className="mt-5 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}</div>
      <div className="mt-5 grid gap-4 xl:grid-cols-3"><Skeleton className="h-80 rounded-2xl xl:col-span-2" /><Skeleton className="h-80 rounded-2xl" /></div>
    </PageContainer></Status>
  );
}

export function ListSkeleton() {
  return (
    <Status><PageContainer wide>
      <Header />
      <div className="mb-4 flex flex-wrap gap-2"><Skeleton className="h-9 w-64 rounded-lg" /><Skeleton className="h-9 w-24 rounded-lg" /><Skeleton className="h-9 w-24 rounded-lg" /></div>
      <div className="rounded-lg border border-border bg-surface p-6 shadow-xs"><SkeletonRows rows={8} /></div>
    </PageContainer></Status>
  );
}

/** Matches the loading state inside RecordPage, so the hand-off is seamless. */
export function RecordSkeleton() {
  return (
    <Status><PageContainer>
      <Skeleton className="h-6 w-24" />
      <div className="mt-6 flex gap-4"><Skeleton className="size-14 rounded-full" /><div className="flex-1 space-y-2"><Skeleton className="h-8 w-72" /><Skeleton className="h-4 w-48" /></div></div>
      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_380px]"><Skeleton className="h-96" /><Skeleton className="h-96" /></div>
    </PageContainer></Status>
  );
}

export function BoardSkeleton() {
  return (
    <Status><PageContainer wide>
      <Header actions={3} />
      <div className="flex gap-4 overflow-hidden">{[0, 1, 2, 3].map((i) => <div key={i} className="w-[256px] shrink-0 space-y-3 rounded-2xl bg-bg-subtle/70 p-3"><Skeleton className="h-6 w-28" />{[0, 1].map((j) => <Skeleton key={j} className="h-28" />)}</div>)}</div>
    </PageContainer></Status>
  );
}

export function CardsSkeleton() {
  return (
    <Status><PageContainer wide>
      <Header actions={1} />
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[380px] rounded-2xl" />)}</div>
    </PageContainer></Status>
  );
}

export function ProjectSkeleton() {
  return (
    <Status><PageContainer wide>
      <Skeleton className="h-6 w-24" /><Skeleton className="mt-4 h-9 w-72" />
      <div className="mt-6 grid gap-5 lg:grid-cols-[260px_1fr_300px]"><Skeleton className="h-96" /><Skeleton className="h-[560px]" /><Skeleton className="h-96" /></div>
    </PageContainer></Status>
  );
}

export function PageSkeleton({ wide }: { wide?: boolean }) {
  return (
    <Status><PageContainer wide={wide}>
      <Header actions={1} />
      <Skeleton className="h-40 rounded-2xl" />
      <Skeleton className="mt-4 h-72 rounded-2xl" />
    </PageContainer></Status>
  );
}

/** Settings sections render inside the settings layout, which stays on screen. */
export function SectionSkeleton() {
  return <Status><div className="space-y-4"><Skeleton className="h-7 w-48" /><Skeleton className="h-96 rounded-2xl" /></div></Status>;
}

/** The skeleton for any /app path, matching the route's own loading.tsx — used while a click is still in flight. */
export function RouteSkeleton({ path }: { path: string }) {
  const [, , section, id] = path.split("/");
  if (!section) return <DashboardSkeleton />;
  if (id && ["leads", "contacts", "companies", "deals"].includes(section)) return <RecordSkeleton />;
  if (["leads", "contacts", "companies"].includes(section)) return <ListSkeleton />;
  if (section === "pipeline" || section === "deals") return <BoardSkeleton />;
  if (section === "projects") return id ? <ProjectSkeleton /> : <CardsSkeleton />;
  return <PageSkeleton wide={["tasks", "calendar", "inbox", "reports", "ai"].includes(section)} />;
}
