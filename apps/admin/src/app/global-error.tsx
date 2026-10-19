"use client";
// Shown when the root layout itself fails, so it brings its own <html>, theme script and styles.
import { PageError, themeScript } from "@crm/ui";
import { useEffect } from "react";
import "./globals.css";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => { console.error(error); }, [error]);
  // React doesn't run <script> tags it renders on the client, so apply the saved theme here as well.
  useEffect(() => { new Function(themeScript)(); }, []);
  return (
    <html lang="en" suppressHydrationWarning>
      <head><title>This page couldn't load</title><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body suppressHydrationWarning>
        <PageError onRetry={() => window.location.reload()} digest={error.digest} details={process.env.NODE_ENV === "development" ? error.message : undefined} />
      </body>
    </html>
  );
}
