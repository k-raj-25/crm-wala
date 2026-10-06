import type { Metadata, Viewport } from "next";
import { themeScript } from "@crm/ui";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CRM Wala — Your entire sales pipeline. Finally simple.", template: "%s · CRM Wala" },
  description: "Manage leads, deals, customers, tasks and revenue from one beautifully simple CRM. 3-day free trial.",
  applicationName: "CRM Wala",
};
export const viewport: Viewport = { themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f6f9" }, { media: "(prefers-color-scheme: dark)", color: "#0a0a11" }], width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
