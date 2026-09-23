import { apiRequest } from "@/api/client";
import { ensureCsrfCookie } from "@/api/auth";
import type { Me, SchoolType } from "@/types/auth";
import type { PlanDurationUnit } from "@/utils/planDuration";

export interface PublicPlan {
  id: number;
  code: string;
  name: string;
  description: string;
  billing_period: "MONTHLY" | "SEMI_ANNUAL" | "ANNUAL" | "CUSTOM";
  price_amount: string;
  currency: string;
  duration_value: number;
  duration_unit: PlanDurationUnit;
  trial_days: number;
  can_self_register: boolean;
  entitlements: Record<string, number | boolean | null>;
}

export interface SchoolRegistrationInput {
  school_name: string;
  school_type: SchoolType;
  manager_name: string;
  manager_mobile: string;
  password: string;
  confirm_password: string;
  plan_id: number;
  terms_accepted: boolean;
}

export function getPublicPlans(signal?: AbortSignal): Promise<PublicPlan[]> {
  return apiRequest<PublicPlan[]>("/auth/registration/plans/", { signal });
}

export async function registerSchool(input: SchoolRegistrationInput): Promise<Me> {
  await ensureCsrfCookie();
  return apiRequest<Me>("/auth/register-school/", {
    method: "POST",
    body: input,
  });
}
