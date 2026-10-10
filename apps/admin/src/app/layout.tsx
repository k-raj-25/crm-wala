import type { Metadata, Viewport } from "next";
import { themeScript } from "@crm/ui";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CRM Wala · Super Admin", template: "%s · Super Admin" },
  description: "Platform administration console",
  robots: { index: false, follow: false },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body suppressHydrationWarning><Providers>{children}</Providers></body>
    </html>
  );
}
