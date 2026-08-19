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

// ---- م8.5: الجسور والأجهزة والمطابقة والحضور الصباحي ----

export interface DeviceFull extends DeviceRow {
  serial_number: string;
  connection_type: string;
  local_ip: string;
  local_port: number | null;
  last_seen_at: string | null;
  last_successful_sync_at: string | null;
  unmatched_events: number;
  test_result: { ok?: boolean; detail?: string } | null;
}

export interface BridgeRow {
  id: number;
  installation_name: string;
  status: string;
  last_seen_at: string | null;
  is_online: boolean;
}

export interface BridgeCredential {
  bridge: BridgeRow;
  credential: string; // يعرض مرة واحدة فقط
}

export interface IdentityRow {
  id: number;
  device_id: number;
  device_name: string;
  external_user_id: string;
  display_name: string;
  status: "MATCHED" | "UNMATCHED" | "CONFLICT" | "IGNORED";
  student_id: number | null;
  student_name: string | null;
}

export interface MorningSummary {
  date: string;
  arrived_total: number;
  on_time: number;
  late: number;
  late_minutes_total: number;
  unmatched_events: number;
  devices_total: number;
  devices_offline: number;
}

export interface LateStudentRow {
  arrival_id: number;
  student_id: number;
  full_name: string;
  grade_name: string;
  section_name: string;
  arrival_time: string;
  raw_late_minutes: number;
  counted_late_minutes: number;
  source: "BIOMETRIC" | "MANUAL";
}

export interface LateList {
  date: string;
  total_late: number;
  students: LateStudentRow[];
  page: number;
  page_size: number;
}

export interface StudentLateHistory {
  student_id: number;
  full_name: string;
  late_count: number;
  total_late_minutes: number;
  entries: {
    date: string;
    arrival_time: string;
    raw_late_minutes: number;
    counted_late_minutes: number;
    source: string;
  }[];
}

export interface ArrivalRow {
  id: number;
  student_id: number;
  attendance_date: string;
  arrival_time: string;
  status: "ON_TIME" | "LATE";
  raw_late_minutes: number;
  counted_late_minutes: number;
  source: string;
}

export const getBridges = (signal?: AbortSignal) =>
  apiRequest<BridgeRow[]>("/device-bridges/", { signal });

export const createBridge = (name: string) =>
  apiRequest<BridgeCredential>("/device-bridges/", { method: "POST", body: { name } });

export const rotateBridge = (bridgeId: number) =>
  apiRequest<BridgeCredential>(`/device-bridges/${bridgeId}/rotate/`, { method: "POST" });

export const getDevicesFull = (signal?: AbortSignal) =>
  apiRequest<DeviceFull[]>("/devices/", { signal });

export const createDevice = (payload: {
  name: string;
  vendor?: string;
  model?: string;
  local_ip?: string;
  local_port?: number | null;
  connection_secret?: string;
}) => apiRequest<DeviceFull>("/devices/", { method: "POST", body: payload });

export const updateDevice = (deviceId: number, payload: Record<string, unknown>) =>
  apiRequest<DeviceFull>(`/devices/${deviceId}/`, { method: "PATCH", body: payload });

export const testDeviceConnection = (deviceId: number) =>
  apiRequest<DeviceFull>(`/devices/${deviceId}/test-connection/`, { method: "POST" });

export const getIdentities = (status?: string, signal?: AbortSignal) =>
  apiRequest<IdentityRow[]>(
    `/device-identities/${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    { signal },
  );

export const mapIdentity = (identityId: number, studentId: number) =>
  apiRequest<IdentityRow>(`/device-identities/${identityId}/map/`, {
    method: "POST",
    body: { student_id: studentId },
  });

export const unmapIdentity = (identityId: number) =>
  apiRequest<IdentityRow>(`/device-identities/${identityId}/unmap/`, { method: "POST" });

export const getMorningSummary = (date: string, signal?: AbortSignal) =>
  apiRequest<MorningSummary>(`/morning/summary/?date=${date}`, { signal });

export const getMorningLate = (
  params: { date: string; grade?: number | ""; search?: string; page?: number },
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams({ date: params.date });
  if (params.grade) query.set("grade", String(params.grade));
  if (params.search) query.set("search", params.search);
  if (params.page) query.set("page", String(params.page));
  return apiRequest<LateList>(`/morning/late/?${query.toString()}`, { signal });
};

export const getStudentLateHistory = (
  studentId: number,
  from: string,
  to: string,
  signal?: AbortSignal,
) =>
  apiRequest<StudentLateHistory>(
    `/morning/students/${studentId}/history/?from=${from}&to=${to}`,
    { signal },
  );

export const createManualArrival = (payload: {
  student_id: number;
  date: string;
  arrival_time: string;
  reason: string;
}) => apiRequest<ArrivalRow>("/morning/arrivals/", { method: "POST", body: payload });

export const correctArrival = (
  arrivalId: number,
  payload: { arrival_time: string; reason: string },
) =>
  apiRequest<ArrivalRow>(`/morning/arrivals/${arrivalId}/correct/`, {
    method: "POST",
    body: payload,
  });

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
