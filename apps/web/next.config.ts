import type { NextConfig } from "next";

// Accepts a full URL or a bare host:port (what Render's private-network `hostport` gives us).
const RAW_API = process.env.API_URL ?? "http://localhost:5000";
const API = /^https?:\/\//.test(RAW_API) ? RAW_API : `http://${RAW_API}`;

const config: NextConfig = {
  transpilePackages: ["@crm/ui"],
  poweredByHeader: false,
  reactStrictMode: true,
  devIndicators: false,
  // Memory-constrained hosts (Render free tier) set SKIP_TYPECHECK=1; types are checked in development / CI with `npm run typecheck`.
  typescript: { ignoreBuildErrors: process.env.SKIP_TYPECHECK === "1" },
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
