"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useTheme } from "@crm/ui";
import { api } from "./api";
import type { CustomFieldDef, Me, Member, NotificationItem, Pipeline, Role, Tag } from "./types";

export const keys = {
  me: ["me"] as const,
  members: ["members"] as const,
  pipelines: ["pipelines"] as const,
  tags: ["tags"] as const,
  customFields: ["custom-fields"] as const,
  roles: ["roles"] as const,
};

/** Switches light/dark/system everywhere it can be changed (Settings, the account menu, the command palette), and saves it to the
    account so Settings always shows what is actually on screen. */
export function useSetTheme() {
  const { setPref } = useTheme(); const qc = useQueryClient();
  return useCallback((p: "light" | "dark" | "system") => {
    setPref(p);
    api.patch<Me>("/api/v1/me/preferences", { theme: p }).then((m) => qc.setQueryData(keys.me, m)).catch(() => {});
  }, [setPref, qc]);
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => api.get<Me>("/api/v1/auth/me"), staleTime: 60_000, retry: false });
}

/** Convenience: permission/feature checks derived from /me. */
export function useAccess() {
  const { data: me } = useMe();
  return useMemo(() => {
    const perms = new Set(me?.permissions ?? []);
    const feats = new Set(me?.features ?? []);
    return {
      me,
      can: (p: string) => perms.has("*") || perms.has(p),
      has: (f: string) => feats.has(f),
      restricted: me?.subscription ? !(me.subscription.access.state === "full" || me.subscription.access.state === "grace") : false,
    };
  }, [me]);
}

export const useMembers = () => useQuery({ queryKey: keys.members, queryFn: () => api.get<Member[]>("/api/v1/team/members"), staleTime: 120_000 });
export const usePipelines = () => useQuery({ queryKey: keys.pipelines, queryFn: () => api.get<Pipeline[]>("/api/v1/pipelines"), staleTime: 120_000 });
export const useTags = () => useQuery({ queryKey: keys.tags, queryFn: () => api.get<Tag[]>("/api/v1/tags"), staleTime: 120_000 });
export const useRoles = () => useQuery({ queryKey: keys.roles, queryFn: () => api.get<Role[]>("/api/v1/roles"), staleTime: 300_000 });
export const useCustomFields = (entity?: string) =>
  useQuery({ queryKey: keys.customFields, queryFn: () => api.get<CustomFieldDef[]>("/api/v1/custom-fields"), staleTime: 120_000, select: (d) => (entity ? d.filter((f) => f.entity_type === entity) : d) });

export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: () => api.page<NotificationItem>("/api/v1/notifications", { per_page: 20 }), refetchInterval: 30_000, staleTime: 15_000 });
}

export function useInvalidate() {
  const qc = useQueryClient();
  return (...k: (readonly unknown[])[]) => k.forEach((key) => qc.invalidateQueries({ queryKey: key as unknown[] }));
}

/** Mutation helper that toasts via caller and invalidates given keys. */
export function useApiMutation<TVars, TRes>(fn: (v: TVars) => Promise<TRes>, opts: { invalidate?: (readonly unknown[])[]; onSuccess?: (r: TRes, v: TVars) => void; onError?: (e: Error) => void } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r, v) => { opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k as unknown[] })); opts.onSuccess?.(r, v); },
    onError: (e) => opts.onError?.(e as Error),
  });
}
