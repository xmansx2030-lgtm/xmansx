export type SchoolRole =
  | "SCHOOL_MANAGER"
  | "VICE_PRINCIPAL"
  | "COUNSELOR"
  | "TEACHER"
  | "GATE_GUARD";
export type SchoolType = "BOYS" | "GIRLS";
export type SchoolCapability = "MORNING_ATTENDANCE";

export interface SchoolSummary {
  id: number;
  name: string;
  slug: string;
  school_type?: SchoolType;
}

export interface MembershipSummary {
  id: number;
  school: SchoolSummary;
  roles: SchoolRole[];
  capabilities?: SchoolCapability[];
  status: string;
}

export interface Invitation {
  id: number;
  school: SchoolSummary;
  roles: SchoolRole[];
  capabilities?: SchoolCapability[];
}

export interface Me {
  id: number;
  mobile: string;
  name: string;
  is_platform_admin: boolean;
  is_platform_owner?: boolean;
  platform_role?: "OWNER" | "OPERATIONS_MANAGER" | "SUPPORT" | "BILLING" | "AUDITOR" | null;
  platform_role_label?: string;
  platform_capabilities?: PlatformCapability[];
  must_change_password: boolean;
  active_school: SchoolSummary | null;
  roles: SchoolRole[];
  capabilities?: SchoolCapability[];
  memberships: MembershipSummary[];
  invitations: Invitation[];
}

export type PlatformCapability =
  | "DASHBOARD_VIEW"
  | "SCHOOLS_VIEW"
  | "SCHOOLS_MANAGE"
  | "SCHOOL_ACCOUNTS_MANAGE"
  | "SUBSCRIPTIONS_MANAGE"
  | "PLANS_VIEW"
  | "PLANS_MANAGE"
  | "TEAM_VIEW"
  | "TEAM_MANAGE";
