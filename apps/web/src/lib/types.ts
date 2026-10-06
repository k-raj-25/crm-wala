export type Id = string;
export type User = { id: Id; name: string; email: string; avatar_url?: string | null; job_role?: string | null; phone?: string | null; email_verified: boolean; mfa_enabled: boolean; preferences: Preferences };
export type Preferences = { theme?: "light" | "dark" | "system"; date_format?: string; currency?: string; timezone?: string; locale?: string; default_pipeline_id?: string; dashboard_widgets?: string[]; sidebar_collapsed?: boolean };
export type LeadStatus = { key: string; label: string; color: string };
export type Access = { state: "full" | "grace" | "restricted" | "suspended"; reason: string | null; seconds_left: number | null; trial_stage: "day1" | "day2" | "final" | "expired" | null; ends_at: string | null };
export type Subscription = { plan_key: string; plan_name: string; status: string; interval: string | null; trial_ends_at: string | null; trial_started_at: string | null; current_period_end: string | null; grace_ends_at: string | null; cancel_at_period_end: boolean; access: Access };
export type Workspace = { id: Id; name: string; slug: string; logo_url?: string | null; brand_color?: string | null; industry?: string | null; company_size?: string | null; website?: string | null; sales_model?: string | null; goals: string[]; timezone: string; currency: string; locale: string; onboarding_completed_at: string | null; onboarding_state: Record<string, unknown>; is_demo: boolean; lead_statuses: LeadStatus[]; plan_key: string };
export type Membership = { workspace_id: Id; name: string; slug: string; role: string; role_name: string; logo_url?: string | null; plan_key: string };
export type Me = {
  user: User; workspaces: Membership[]; workspace: Workspace | null; impersonating: boolean;
  role?: { key: string; name: string }; permissions?: string[]; features?: string[]; limits?: Record<string, number | null>; subscription?: Subscription;
};
export type PersonRef = { id: Id; name: string; avatar_url?: string | null; email?: string };
export type Related = { type: "lead" | "contact" | "company" | "deal"; id: Id; label: string };
export type Lead = {
  id: Id; first_name: string; last_name: string | null; name?: string; email: string | null; phone: string | null; company_name: string | null; job_title: string | null; source: string | null; status: string;
  owner_id: Id | null; owner: PersonRef | null; score: number; score_reasons: { label: string; points: number }[]; tags: string[]; location: string | null; description: string | null; custom: Record<string, unknown>;
  last_contacted_at: string | null; next_follow_up_at: string | null; created_at: string; converted_at: string | null; converted_contact_id: Id | null; converted_deal_id: Id | null;
};
export type Contact = {
  id: Id; first_name: string; last_name: string | null; name: string; email: string | null; phone: string | null; job_title: string | null; company_id: Id | null; company: { id: Id; name: string } | null;
  owner_id: Id | null; owner: PersonRef | null; location: string | null; socials: Record<string, string>; tags: string[]; description: string | null; custom: Record<string, unknown>;
  last_contacted_at: string | null; last_activity_at: string | null; created_at: string; avatar_url?: string | null;
};
export type Company = {
  id: Id; name: string; website: string | null; industry: string | null; size: string | null; location: string | null; annual_revenue: number | null; phone: string | null; owner_id: Id | null; owner: PersonRef | null;
  tags: string[]; description: string | null; custom: Record<string, unknown>; contacts_count: number; open_deals_count: number; open_deals_value: number; created_at: string; last_activity_at: string | null;
};
export type Stage = { id: Id; name: string; position: number; probability: number; kind: "open" | "won" | "lost"; color: string | null; pipeline_id: Id };
export type Pipeline = { id: Id; name: string; is_default: boolean; currency: string; stages: Stage[] };
export type Deal = {
  id: Id; name: string; company: { id: Id; name: string } | null; contact: { id: Id; name: string } | null; company_id: Id | null; contact_id: Id | null; pipeline_id: Id; stage_id: Id;
  stage: { id: Id; name: string; kind: "open" | "won" | "lost"; color: string | null; position: number }; value: number; currency: string; probability: number; weighted_value: number; priority: "low" | "medium" | "high" | "urgent";
  expected_close_date: string | null; owner_id: Id | null; owner: PersonRef | null; source: string | null; tags: string[]; description: string | null; custom: Record<string, unknown>; status: "open" | "won" | "lost";
  lead_score: number; days_in_stage: number | null; created_at: string; closed_at: string | null; last_activity_at: string | null; lost_reason: string | null; position: number;
};
export type Task = {
  id: Id; title: string; description: string | null; assignee_id: Id | null; assignee: PersonRef | null; due_at: string | null; priority: "low" | "medium" | "high" | "urgent"; status: "todo" | "in_progress" | "completed";
  kind: "task" | "follow_up" | "deadline"; related: Related[]; lead_id: Id | null; contact_id: Id | null; company_id: Id | null; deal_id: Id | null; completed_at: string | null; created_at: string;
};
export type Note = { id: Id; body: string; author: PersonRef | null; pinned: boolean; created_at: string; related: Related[] };
export type Call = { id: Id; direction: string; status: string; outcome: string | null; phone: string | null; scheduled_at: string | null; occurred_at: string | null; duration_seconds: number | null; notes: string | null; owner: PersonRef | null; created_at: string; related: Related[] };
export type Meeting = { id: Id; title: string; description: string | null; starts_at: string; ends_at: string; location: string | null; meeting_url: string | null; status: string; attendees: { name: string; email: string }[]; summary: string | null; owner: PersonRef | null; related: Related[] };
export type EmailMsg = { id: Id; direction: "inbound" | "outbound"; status: string; subject: string; body: string; from_address: string | null; to_addresses: string[]; sent_at: string | null; scheduled_at: string | null; opens: number; tracking_id: string | null; owner: PersonRef | null; created_at: string; related: Related[] };
export type Activity = { id: Id; type: string; title: string; body: string | null; occurred_at: string; user: PersonRef | null; related: Related[]; data: Record<string, unknown> };
export type Member = { id: Id; user_id: Id; name: string; email: string; avatar_url: string | null; status: string; role: { id: Id; key: string; name: string; rank: number }; team_id: Id | null; last_login_at: string | null; joined_at: string; mfa_enabled: boolean };
export type Role = { id: Id; key: string; name: string; description: string | null; permissions: string[]; is_system: boolean; rank: number; workspace_id: Id | null };
export type Tag = { id: Id; name: string; color: string | null };
export type CustomFieldDef = { id: Id; entity_type: "lead" | "contact" | "company" | "deal"; key: string; label: string; field_type: string; options: string[]; required: boolean; position: number };
export type SavedView = { id: Id; entity_type: string; name: string; filters: Record<string, string>; sort: string | null; columns: string[]; shared: boolean; owner_id: Id };
export type NotificationItem = { id: Id; type: string; title: string; body: string | null; link: string | null; read_at: string | null; created_at: string };
export type Plan = { key: string; name: string; tagline: string | null; currency: string; price_monthly: number | null; price_annual: number | null; limits: Record<string, number | null>; features: string[]; highlights: string[]; is_custom: boolean; is_trial: boolean };
export type CalendarEvent = { id: Id; kind: "meeting" | "call" | "task" | "follow_up" | "deadline"; title: string; start: string; end: string; status: string; location?: string | null; priority?: string; entity: { type: string; id: Id } };
