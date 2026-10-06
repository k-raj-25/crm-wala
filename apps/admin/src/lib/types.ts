export type Admin = { id: string; email: string; name: string; role: "superadmin" | "support" | "finance"; mfa_enabled: boolean; last_login_at: string | null; status?: string };
export type AdminMe = { admin: Admin; mfa_verified: boolean; config: { require_2fa: boolean } };
export type Meta = { page: number; per_page: number; total: number; pages: number };
