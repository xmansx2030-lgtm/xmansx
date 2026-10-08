import { withReturnTo } from "@/features/auth/returnTo";
import type { Me } from "@/types/auth";

/** Parent access is independent of a staff membership and active school. */
export function authenticatedDestination(
  me: Me,
  returnTo: string | null = null,
): string {
  if (me.must_change_password) return "/change-password";
  if (me.is_platform_admin) return "/platform";
  if (returnTo?.startsWith("/parent")) return returnTo;
  if (me.active_school) return returnTo ?? "/workspace";
  if (
    me.has_parent_portal &&
    me.memberships.length === 0 &&
    me.invitations.length === 0
  )
    return "/parent";
  return withReturnTo("/select-school", returnTo);
}
