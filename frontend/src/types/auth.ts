export type SchoolRole = "SCHOOL_MANAGER" | "VICE_PRINCIPAL" | "COUNSELOR" | "TEACHER";

export interface SchoolSummary {
  id: number;
  name: string;
  slug: string;
}

export interface MembershipSummary {
  id: number;
  school: SchoolSummary;
  roles: SchoolRole[];
  status: string;
}

export interface Invitation {
  id: number;
  school: SchoolSummary;
  roles: SchoolRole[];
}

export interface Me {
  id: number;
  mobile: string;
  name: string;
  is_platform_admin: boolean;
  must_change_password: boolean;
  active_school: SchoolSummary | null;
  roles: SchoolRole[];
  memberships: MembershipSummary[];
  invitations: Invitation[];
}
