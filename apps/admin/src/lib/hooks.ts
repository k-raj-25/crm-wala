"use client";
import { useQuery } from "@tanstack/react-query";
import { A, api } from "./api";
import type { AdminMe } from "./types";

export const useAdmin = () => useQuery({ queryKey: ["admin-me"], queryFn: () => api.get<AdminMe>(`${A}/auth/me`), staleTime: 60_000, retry: false });

/** Role helpers mirroring the API (superadmin can do everything). */
export function useCan() {
  const { data } = useAdmin();
  const role = data?.admin.role;
  return (...roles: string[]) => role === "superadmin" || (!!role && roles.includes(role));
}
