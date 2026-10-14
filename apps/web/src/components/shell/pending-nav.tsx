"use client";
import { usePathname } from "next/navigation";
import * as React from "react";

/**
 * Optimistic navigation. The App Router keeps the old page on screen until the new route's payload arrives — which
 * on a cold server (or a first `next dev` compile) can take many seconds, even with loading.tsx. So the moment an
 * in-app link is clicked we record where the user is going, and the shell swaps to that page's skeleton (and the
 * sidebar highlight) right away. The real route replaces it as soon as Next.js commits the navigation.
 */
let pending: string | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const set = (p: string | null) => { if (p !== pending) { pending = p; emit(); } };

/** Call before `router.push(href)` so programmatic navigations get the same instant feedback as links. */
export function startNavigation(href: string) {
  if (typeof window === "undefined") return;
  let url: URL;
  try { url = new URL(href, window.location.href); } catch { return; }
  if (url.origin !== window.location.origin || !url.pathname.startsWith("/app") || url.pathname === window.location.pathname) return;
  set(url.pathname);
}

/** The path being navigated to, or null when nothing is in flight. */
export function usePendingPath() {
  return React.useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => pending, () => null);
}

/** Watches clicks on in-app links and clears the pending path once the route has actually changed. */
export function PendingNavigation() {
  const pathname = usePathname();
  React.useEffect(() => { set(null); }, [pathname]);
  React.useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]");
      if (!(a instanceof HTMLAnchorElement) || a.hasAttribute("download") || (a.target && a.target !== "_self")) return;
      startNavigation(a.href);
    };
    const clear = () => set(null);
    document.addEventListener("click", onClick);
    window.addEventListener("popstate", clear);
    return () => { document.removeEventListener("click", onClick); window.removeEventListener("popstate", clear); };
  }, []);
  return null;
}

/** `router.push` with the same instant skeleton a link click gets. */
export function navigate(router: { push: (href: string) => void }, href: string) {
  startNavigation(href);
  router.push(href);
}
