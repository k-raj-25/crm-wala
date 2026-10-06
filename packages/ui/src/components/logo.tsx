import { cn } from "../lib/cn";

export function LogoMark({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7c74ff" /><stop offset="1" stopColor="#4f46e5" /></linearGradient></defs>
      <rect width="32" height="32" rx="9" fill="url(#lg)" />
      <path d="M10 21.5c0-3.6 2.6-5.6 6-5.6 2.2 0 3.8.8 4.8 2" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" fill="none" />
      <circle cx="21.5" cy="11" r="2.4" fill="#fff" />
      <path d="M11 11.2h5" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" opacity=".55" />
    </svg>
  );
}

export function Logo({ className, collapsed, name = "CRM Wala" }: { className?: string; collapsed?: boolean; name?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      {!collapsed && <span className="text-[16px] font-semibold tracking-tight text-fg">{name}</span>}
    </span>
  );
}
