import { apiRequest } from "@/api/client";

export interface HealthResponse {
  status: "ok";
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health/", { signal });
}
