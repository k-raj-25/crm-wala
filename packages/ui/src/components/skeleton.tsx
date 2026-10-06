import { cn } from "../lib/cn";

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cn("skeleton h-4 w-full", className)} style={style} aria-hidden />;
}
export function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-8 rounded-full" /><Skeleton className="h-4 flex-1" style={{ maxWidth: `${60 + ((i * 17) % 35)}%` }} /><Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}
