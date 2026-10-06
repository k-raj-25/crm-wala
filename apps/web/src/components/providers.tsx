"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, ToastProvider, TooltipProvider } from "@crm/ui";
import { useState } from "react";
import { ApiError } from "@crm/ui";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000, refetchOnWindowFocus: false,
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 0) && count < 2,
      },
    },
  }));
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider><TooltipProvider><ToastProvider>{children}</ToastProvider></TooltipProvider></ThemeProvider>
    </QueryClientProvider>
  );
}
