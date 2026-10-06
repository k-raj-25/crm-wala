"use client";
import { useParams } from "next/navigation";
import { Suspense } from "react";
import { ErrorState } from "@crm/ui";
import { CustomFieldSettings, EmailSettings, LeadStatusSettings, PipelineSettings, TagSettings } from "@/components/settings/config";
import { AuditSettings, DataSettings } from "@/components/settings/data";
import { NotificationSettings, ProfileSettings, SecuritySettings } from "@/components/settings/personal";
import { RolesSettings, TeamSettings, WorkspaceSettings } from "@/components/settings/workspace";
import { useAccess } from "@/lib/queries";

const SECTIONS: Record<string, () => React.ReactNode> = {
  profile: () => <ProfileSettings />, notifications: () => <NotificationSettings />, security: () => <SecuritySettings />, workspace: () => <WorkspaceSettings />,
  team: () => <TeamSettings />, roles: () => <RolesSettings />, pipelines: () => <PipelineSettings />, "lead-statuses": () => <LeadStatusSettings />, "custom-fields": () => <CustomFieldSettings />,
  tags: () => <TagSettings />, email: () => <EmailSettings />, data: () => <DataSettings />, audit: () => <AuditSettings />,
};
export default function Page() {
  const { section } = useParams<{ section: string }>(); const { can } = useAccess();
  const render = SECTIONS[section];
  if (!render) return <ErrorState kind="generic" title="Page not found" description="That settings page doesn't exist." />;
  if (section === "audit" && !can("audit.read")) return <ErrorState kind="permission" />;
  return <Suspense>{render()}</Suspense>;
}
