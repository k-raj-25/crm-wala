import type { NextConfig } from "next";

const API = process.env.API_URL ?? "http://localhost:5000";

const config: NextConfig = {
  transpilePackages: ["@crm/ui"],
  poweredByHeader: false,
  reactStrictMode: true,
  // The browser only ever talks to this origin; /api/* is proxied to Flask so auth cookies are same-site and
  // the admin API (/admin-api) is deliberately NOT exposed through the customer app.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Frame-Options", value: "DENY" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
      ],
    }];
  },
};
export default config;
