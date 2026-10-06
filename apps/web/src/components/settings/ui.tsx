"use client";
import * as React from "react";
import { Card, CardBody, CardHeader, cn } from "@crm/ui";

export function SettingsSection({ title, description, actions, children, className }: { title: string; description?: string; actions?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <Card className={className}><CardHeader title={title} description={description} actions={actions} /><CardBody>{children}</CardBody></Card>;
}
export const FieldRow = ({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) => (
  <div className={cn("grid gap-2 py-4 sm:grid-cols-[220px_1fr] sm:gap-8", className)}><div><p className="text-sm font-medium">{label}</p>{hint && <p className="mt-0.5 text-xs text-fg-muted">{hint}</p>}</div><div className="min-w-0 max-w-md">{children}</div></div>
);
export const Divided = ({ children }: { children: React.ReactNode }) => <div className="divide-y divide-border">{children}</div>;
