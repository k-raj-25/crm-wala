"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, ThemeProvider, ToastProvider, TooltipProvider } from "@crm/ui";
import { StepUpProvider } from "@/components/step-up";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 20_000, refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2 } },
  }));
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider><TooltipProvider><ToastProvider><StepUpProvider>{children}</StepUpProvider></ToastProvider></TooltipProvider></ThemeProvider>
    </QueryClientProvider>
  );
}
