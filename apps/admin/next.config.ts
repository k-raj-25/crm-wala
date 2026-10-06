import type { NextConfig } from "next";

// Accepts a full URL or a bare host:port (what Render's private-network `hostport` gives us).
const RAW_API = process.env.API_URL ?? "http://localhost:5000";
const API = /^https?:\/\//.test(RAW_API) ? RAW_API : `http://${RAW_API}`;

const config: NextConfig = {
  transpilePackages: ["@crm/ui"],
  poweredByHeader: false,
  reactStrictMode: true,
  devIndicators: false,
  // Only the admin API is proxied here; the customer API is deliberately unreachable from the admin origin.
  async rewrites() {
    return [{ source: "/admin-api/:path*", destination: `${API}/admin-api/:path*` }];
  },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Frame-Options", value: "DENY" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "X-Robots-Tag", value: "noindex, nofollow" },
        { key: "Cache-Control", value: "no-store" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
      ],
    }];
  },
};
export default config;
