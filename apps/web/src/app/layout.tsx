import type { Metadata, Viewport } from "next";
import { themeScript } from "@crm/ui";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CRM Wala — The simple CRM for real estate. See every flat at a glance.", template: "%s · CRM Wala" },
  description: "The CRM for realtors who are tired of complicated CRMs. See every tower, floor and flat — vacant, held, sold or rented — in one picture. 3-day free trial.",
  applicationName: "CRM Wala",
};
export const viewport: Viewport = { themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f6f9" }, { media: "(prefers-color-scheme: dark)", color: "#0a0a11" }], width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body suppressHydrationWarning><Providers>{children}</Providers></body>
    </html>
  );
}
