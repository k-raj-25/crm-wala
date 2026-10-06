import { createApi } from "@crm/ui";

export const api = createApi({
  csrfCookie: "crm_csrf",
  refreshPath: "/api/v1/auth/refresh",
  onSessionExpired: () => {
    if (typeof window === "undefined") return;
    const p = window.location.pathname;
    if (p.startsWith("/app") || p.startsWith("/onboarding")) window.location.href = `/login?expired=1&next=${encodeURIComponent(p + window.location.search)}`;
  },
});
