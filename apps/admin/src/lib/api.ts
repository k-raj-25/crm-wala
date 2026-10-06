import { createApi } from "@crm/ui";

export const api = createApi({
  csrfCookie: "adm_csrf",
  refreshPath: "/admin-api/v1/auth/refresh",
  onSessionExpired: () => {
    if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
    window.location.href = `/login?expired=1&next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  },
});
export const A = "/admin-api/v1";
