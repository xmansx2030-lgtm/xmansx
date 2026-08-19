import { apiRequest } from "@/api/client";

export interface DeviceRow {
  id: number;
  name: string;
  vendor: string;
  model: string;
  status: string;
  is_active: boolean;
}

export interface RosterJob {
  id: number;
  device_id: number;
  device_name: string;
  status: string;
  roster_version: string;
  device_roster_version: string;
  matched_count: number;
  create_count: number;
  update_count: number;
  delete_count: number;
  conflict_count: number;
  student_count: number;
  device_user_count: number;
  ready_at: string | null;
  approved_at: string | null;
}

export interface RosterItem {
  id: number;
  student_id: number | null;
  student_name: string | null;
  external_user_id: string;
  action: "MATCHED" | "CREATE" | "UPDATE" | "DELETE" | "CONFLICT";
  status: string;
  reason: string;
  error_code: string;
  safe_before_snapshot: Record<string, unknown>;
  safe_after_snapshot: Record<string, unknown>;
}

export const getDevices = (signal?: AbortSignal) =>
  apiRequest<DeviceRow[]>("/devices/", { signal });

export const analyzeDeviceRoster = (deviceId: number) =>
  apiRequest<RosterJob>(`/devices/${deviceId}/roster-sync/analyze/`, { method: "POST" });

export const getRosterJob = (jobId: number, signal?: AbortSignal) =>
  apiRequest<RosterJob>(`/device-roster-syncs/${jobId}/`, { signal });

export const getRosterItems = (jobId: number, action?: string, signal?: AbortSignal) =>
  apiRequest<RosterItem[]>(
    `/device-roster-syncs/${jobId}/items/${action ? `?action=${encodeURIComponent(action)}` : ""}`,
    { signal },
  );

export const approveRosterJob = (jobId: number) =>
  apiRequest<RosterJob>(`/device-roster-syncs/${jobId}/approve/`, { method: "POST" });

export const retryRosterJob = (jobId: number) =>
  apiRequest<RosterJob>(`/device-roster-syncs/${jobId}/retry/`, { method: "POST" });
