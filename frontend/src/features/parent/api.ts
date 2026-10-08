import { apiRequest } from "@/api/client";
import type { Me } from "@/types/auth";
import type { ReasonType } from "@/features/excuses/api";

export type RelationStatus =
  | "PENDING"
  | "ACTIVE"
  | "SUSPENDED_CONTACT_REVIEW"
  | "REJECTED"
  | "REVOKED"
  | "UNAVAILABLE";
export type RequestStatus =
  "PENDING" | "NEEDS_INFO" | "APPROVED" | "REJECTED" | "CANCELLED";
export interface ParentDay {
  date: string;
  absence_status: "FULL" | "PARTIAL" | "NONE" | "UNDETERMINED";
  completeness_status: string;
  expected_periods: number;
  submitted_periods: number;
  present_periods: number;
  absent_periods: number;
  excused_absent_periods: number;
  unexcused_absent_periods: number;
  updated_at: string | null;
}
export interface Child {
  relation_id: number;
  school: { id: number; name: string };
  student: {
    id: number;
    full_name: string;
    grade_name: string | null;
    section_name: string | null;
    department?: string;
  } | null;
  status: RelationStatus;
  today: ParentDay | null;
  new_notifications?: number;
  required_actions?: number;
}
export interface Morning {
  status: string;
  arrival_time: string | null;
  counted_late_minutes: number;
  updated_at: string | null;
}
export interface ParentPeriod {
  session_id: number | null;
  attendance_date: string;
  period_sequence: number;
  sequence: number;
  name: string;
  start_time: string | null;
  end_time: string | null;
  status: string;
  status_label: string;
  updated_at: string | null;
}
export interface ChildDetail {
  child: Child;
  today: ParentDay;
  periods: ParentPeriod[];
  morning: Morning;
}
export interface ParentHistory {
  results: Array<ParentDay & { morning?: Morning | null }>;
  from_date: string;
  to_date: string;
  summary: {
    full_absence_days: number;
    partial_absence_days: number;
    excused_absent_periods: number;
    unexcused_absent_periods: number;
    present_periods: number;
    absent_periods: number;
    morning_late_days: number;
    counted_late_minutes: number;
    incomplete_days: number;
  };
}
export interface Attachment {
  id: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
}
export interface ExcuseRequest {
  id: number;
  type: "EXCUSE";
  relation_id?: number;
  student_id: number;
  student_name?: string;
  status: RequestStatus;
  reason_type: ReasonType;
  notes: string;
  targets: Array<{ attendance_date: string; period_sequence: number | null }>;
  decision_note: string;
  administrative_excuse_id: number | null;
  created_at: string;
  updated_at: string;
  attachments: Attachment[];
}
export interface CorrectionRequest {
  id: number;
  type: "CORRECTION";
  relation_id?: number;
  student_id: number;
  student_name?: string;
  session_id: number;
  attendance_date: string;
  period_sequence: number;
  status: RequestStatus;
  reason: string;
  decision_note: string;
  created_at: string;
  updated_at: string;
  session_updated_at?: string | null;
}
export type FamilyRequest = ExcuseRequest | CorrectionRequest;
export interface ParentWarning {
  id: number;
  warning_type: string;
  level: string;
  status: string;
  issued_at: string;
  acknowledged_at: string | null;
  documents: Array<{
    publication_id: number;
    document_type: string;
    status: string;
  }>;
}
export interface Publication {
  id: number;
  title: string;
  body: string;
  required_action: string;
  due_at: string | null;
  published_at: string;
  acknowledged_at: string | null;
  document: { id: number; type: string } | null;
  ack_count?: number;
  acknowledgements?: Array<{
    relation_id: number;
    parent_name: string;
    acknowledged_at: string;
  }>;
}
export interface StaffAcknowledgement {
  id: number;
  type: "WARNING" | "PUBLICATION";
  student_name: string;
  parent_name: string;
  acknowledged_at: string;
  target_id: number;
  relation_id: number;
  student_id: number;
}
export interface ParentNotification {
  id: number;
  relation_id: number;
  kind: string;
  title: string;
  body: string;
  state: string;
  requires_action: boolean;
  created_at: string;
  read_at: string | null;
  action_completed_at: string | null;
  student_name?: string | null;
  school_name?: string | null;
}
export interface RegistrationMetadata {
  school_name: string;
  school_id: number;
  enabled: boolean;
}
export interface RegistrationInput {
  name: string;
  mobile: string;
  student_identifier: string;
  relationship_type: string;
}
export interface ActivationMetadata {
  school_name: string;
  requires_login: boolean;
  account_exists: boolean;
  status: string;
}
export interface ParentSettings {
  enabled: boolean;
  registration_url: string | null;
  stats: Record<string, number>;
}
export interface Registration {
  id: number;
  name: string;
  mobile: string;
  mobile_masked?: string;
  student_identifier?: string;
  relationship_type: string;
  status: RequestStatus | "ACTIVATED";
  created_at: string;
  decision_reason?: string;
  applicant_note?: string;
}
export interface StudentMatch {
  id: number;
  full_name: string;
  national_id_masked?: string;
  grade_name?: string;
  section_name?: string;
  guardian_mobile_masked?: string;
  guardian_name?: string;
}
export interface RegistrationDetail {
  request: Registration;
  student_match: StudentMatch | null;
  sibling_candidates: StudentMatch[];
  existing_relations: Array<{
    id: number;
    status: RelationStatus;
    user_name?: string;
    student_id?: number;
  }>;
  activations: ActivationDeliveryRecord[];
}
export type ActivationDeliveryStatus =
  "PENDING" | "SENDING" | "SENT" | "FAILED" | "UNKNOWN" | "MANUAL";
export interface ActivationDeliveryRecord {
  id: number;
  delivery_status: ActivationDeliveryStatus;
  failure_code: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  revoked_at: string | null;
}
export interface RegistrationDecisionResult {
  request: Registration;
  delivery_status?: ActivationDeliveryStatus;
  activation_url?: string;
}
export interface StaffRelation {
  id: number;
  relation_id?: number;
  user_name?: string;
  parent_name: string;
  mobile_masked?: string;
  student_id: number;
  student_name: string;
  status: RelationStatus;
  approval_revision: number;
  contact_bound?: boolean;
}
export interface ContactReview {
  id: number;
  student_id: number;
  student_name: string;
  previous_revision: number;
  current_revision: number;
  source: string;
  reason: string;
  actor_name: string | null;
  created_at: string;
  resolved_at: string | null;
}
export interface RecipientBlock {
  id: number;
  student_id: number;
  student_name?: string;
  mobile_masked: string;
  reason: string;
  resolved_at: string | null;
}
export interface GlobalMobileChange {
  id: number;
  status: string;
  new_mobile_masked: string;
  created_at: string;
}
export interface Paged<T> {
  results: T[];
  count: number;
  next: string | null;
  previous: string | null;
}
export interface ItemPaged<T> {
  items: T[];
  count: number;
  next: string | null;
  previous: string | null;
}
function pageQuery(page: number, status = "") {
  const params = new URLSearchParams();
  if (page > 1) params.set("page", String(page));
  if (status) params.set("status", status);
  return params.size ? `?${params}` : "";
}
export const parentKey = (userId: number | undefined, ...parts: unknown[]) =>
  ["parent", userId, ...parts] as const;
const childPath = (relation: number) => `/parent/children/${relation}`;
const staffPath = "/staff/parents";
export const getRegistration = (schoolToken: string, signal?: AbortSignal) =>
  apiRequest<RegistrationMetadata>(
    `/parent/registration/${encodeURIComponent(schoolToken)}/`,
    { signal },
  );
export const registerParent = (schoolToken: string, body: RegistrationInput) =>
  apiRequest<{ message: string; receipt_token: string }>(
    `/parent/registration/${encodeURIComponent(schoolToken)}/`,
    { method: "POST", body },
  );
export const getRegistrationStatus = (
  receipt_token: string,
  applicant_note?: string,
) =>
  apiRequest<{ status: string; message: string }>(
    "/parent/registration/status/",
    {
      method: "POST",
      body: { receipt_token, ...(applicant_note ? { applicant_note } : {}) },
    },
  );
export const checkActivation = (token: string, signal?: AbortSignal) =>
  apiRequest<ActivationMetadata>("/parent/activation/check/", {
    method: "POST",
    body: { token },
    signal,
  });
export const activateParent = (
  token: string,
  password?: string,
  confirm?: string,
) =>
  apiRequest<Me>("/parent/activation/", {
    method: "POST",
    body: {
      token,
      ...(password
        ? { new_password: password, confirm_password: confirm }
        : {}),
    },
  });
export const getChildren = (signal?: AbortSignal, page = 1) =>
  apiRequest<Paged<Child>>(`/parent/children/${pageQuery(page)}`, { signal });
export const changeParentPassword = (
  current_password: string,
  new_password: string,
  confirm_password: string,
) =>
  apiRequest<{ message: string }>("/parent/account/password/", {
    method: "POST",
    body: { current_password, new_password, confirm_password },
  });
export const getChild = (
  relation: number,
  signal?: AbortSignal,
  date?: string,
) =>
  apiRequest<ChildDetail>(
    `${childPath(relation)}/${date ? `?date=${date}` : ""}`,
    { signal },
  );
export const getHistory = (
  relation: number,
  from: string,
  to: string,
  signal?: AbortSignal,
) =>
  apiRequest<ParentHistory>(
    `${childPath(relation)}/history/?from_date=${from}&to_date=${to}`,
    { signal },
  );
export const getRequests = (signal?: AbortSignal, page = 1) =>
  apiRequest<ItemPaged<FamilyRequest>>(`/parent/requests/${pageQuery(page)}`, {
    signal,
  });
export const createExcuseRequest = (
  relation: number,
  body: {
    reason_type: ReasonType;
    notes: string;
    targets: ExcuseRequest["targets"];
  },
) =>
  apiRequest<ExcuseRequest>(`${childPath(relation)}/excuses/`, {
    method: "POST",
    body,
  });
export const uploadRequestAttachment = (
  relation: number,
  id: number,
  file: File,
) => {
  const body = new FormData();
  body.append("file", file);
  return apiRequest<Attachment>(
    `${childPath(relation)}/excuses/${id}/attachments/`,
    { method: "POST", body },
  );
};
export const attachmentDownloadUrl = (
  relation: number,
  request: number,
  attachment: number,
) =>
  `/api/v1${childPath(relation)}/excuses/${request}/attachments/${attachment}/download/`;
export const resubmitExcuseRequest = (
  relation: number,
  id: number,
  notes: string,
) =>
  apiRequest<ExcuseRequest>(`${childPath(relation)}/excuses/${id}/resubmit/`, {
    method: "POST",
    body: { notes },
  });
export const cancelExcuseRequest = (relation: number, id: number) =>
  apiRequest<ExcuseRequest>(`${childPath(relation)}/excuses/${id}/cancel/`, {
    method: "POST",
  });
export const createCorrectionRequest = (
  relation: number,
  session_id: number,
  reason: string,
) =>
  apiRequest<CorrectionRequest>(`${childPath(relation)}/corrections/`, {
    method: "POST",
    body: { session_id, reason },
  });
export const getWarnings = (relation: number, signal?: AbortSignal, page = 1) =>
  apiRequest<ItemPaged<ParentWarning>>(
    `${childPath(relation)}/warnings/${pageQuery(page)}`,
    { signal },
  );
export const acknowledgeWarning = (relation: number, id: number) =>
  apiRequest(`${childPath(relation)}/warnings/${id}/acknowledge/`, {
    method: "POST",
  });
export const getPublications = (
  relation: number,
  signal?: AbortSignal,
  page = 1,
) =>
  apiRequest<ItemPaged<Publication>>(
    `${childPath(relation)}/publications/${pageQuery(page)}`,
    { signal },
  );
export const acknowledgePublication = (relation: number, id: number) =>
  apiRequest(`${childPath(relation)}/publications/${id}/acknowledge/`, {
    method: "POST",
  });
export const publicationDownloadUrl = (relation: number, id: number) =>
  `/api/v1${childPath(relation)}/publications/${id}/download/`;
export const getNotifications = (
  signal?: AbortSignal,
  page = 1,
  relation?: number,
) => {
  const params = new URLSearchParams(pageQuery(page).slice(1));
  if (relation && Number.isSafeInteger(relation) && relation > 0)
    params.set("relation_id", String(relation));
  return apiRequest<ItemPaged<ParentNotification>>(
    `/parent/notifications/${params.size ? `?${params}` : ""}`,
    { signal },
  );
};
export const notificationRead = (id: number) =>
  apiRequest(`/parent/notifications/${id}/read/`, { method: "POST" });
export const notificationComplete = (id: number) =>
  apiRequest(`/parent/notifications/${id}/complete-action/`, {
    method: "POST",
  });
export const getParentSettings = (signal?: AbortSignal) =>
  apiRequest<ParentSettings>(`${staffPath}/settings/`, { signal });
export const setParentSettings = (enabled: boolean) =>
  apiRequest<ParentSettings>(`${staffPath}/settings/`, {
    method: "PATCH",
    body: { enabled },
  });
export const getRegistrations = (signal?: AbortSignal, page = 1, status = "") =>
  apiRequest<Paged<Registration>>(
    `${staffPath}/registrations/${pageQuery(page, status)}`,
    { signal },
  );
export const getRegistrationDetail = (id: number, signal?: AbortSignal) =>
  apiRequest<RegistrationDetail>(`${staffPath}/registrations/${id}/`, {
    signal,
  });
export const reissueActivation = (
  id: number,
  delivery: "SMS" | "MANUAL",
  verification_note: string,
) =>
  apiRequest<{
    delivery_status: ActivationDeliveryStatus;
    activation_url?: string;
  }>(`${staffPath}/registrations/${id}/activation/`, {
    method: "POST",
    body: { delivery, verification_note },
  });
export const decideRegistration = (
  id: number,
  body: {
    decision: string;
    student_id?: number;
    verification_note: string;
    decision_reason: string;
    contact_bound: boolean;
    delivery: "SMS" | "MANUAL";
  },
) =>
  apiRequest<RegistrationDecisionResult>(
    `${staffPath}/registrations/${id}/decision/`,
    { method: "POST", body },
  );
export const getStaffRelations = (
  signal?: AbortSignal,
  page = 1,
  status = "",
) =>
  apiRequest<Paged<StaffRelation>>(
    `${staffPath}/relations/${pageQuery(page, status)}`,
    { signal },
  );
export const decideRelation = (
  id: number,
  status: RelationStatus,
  reason: string,
  verification_note: string,
) =>
  apiRequest(`${staffPath}/relations/${id}/decision/`, {
    method: "POST",
    body: { status, reason, verification_note },
  });
export const getStaffRequests = (signal?: AbortSignal, page = 1) =>
  apiRequest<
    ItemPaged<FamilyRequest> & {
      excuses: ExcuseRequest[];
      corrections: CorrectionRequest[];
    }
  >(`${staffPath}/requests/${pageQuery(page)}`, { signal });
export const decideFamilyRequest = (
  type: FamilyRequest["type"],
  id: number,
  decision: string,
  note: string,
  expected_updated_at?: string | null,
) =>
  apiRequest(
    `${staffPath}/${type === "EXCUSE" ? "excuses" : "corrections"}/${id}/decision/`,
    {
      method: "POST",
      body: {
        decision,
        note,
        ...(expected_updated_at ? { expected_updated_at } : {}),
      },
    },
  );
export const staffAttachmentDownloadUrl = (
  request: number,
  attachment: number,
) =>
  `/api/v1${staffPath}/excuses/${request}/attachments/${attachment}/download/`;
export const getStaffPublications = (signal?: AbortSignal, page = 1) =>
  apiRequest<ItemPaged<Publication>>(
    `${staffPath}/publications/${pageQuery(page)}`,
    { signal },
  );
export const getStaffAcknowledgements = (signal?: AbortSignal, page = 1) =>
  apiRequest<ItemPaged<StaffAcknowledgement>>(
    `${staffPath}/acknowledgements/${pageQuery(page)}`,
    { signal },
  );
export const publishFamilyContent = (body: {
  student_id: number;
  title: string;
  body: string;
  required_action: string;
  due_at?: string;
  case_id?: number;
  document_id?: number;
}) =>
  apiRequest<Publication>(`${staffPath}/publications/`, {
    method: "POST",
    body,
  });
export const revokeFamilyPublication = (id: number, reason: string) =>
  apiRequest(`${staffPath}/publications/${id}/revoke/`, {
    method: "POST",
    body: { reason },
  });
export const getContactReviews = (signal?: AbortSignal, page = 1) =>
  apiRequest<Paged<ContactReview>>(
    `${staffPath}/contact-reviews/${pageQuery(page)}`,
    { signal },
  );
export const getRecipientBlocks = (signal?: AbortSignal, page = 1) =>
  apiRequest<Paged<RecipientBlock>>(
    `${staffPath}/recipient-blocks/${pageQuery(page)}`,
    { signal },
  );
export const getGlobalMobileChanges = (signal?: AbortSignal, page = 1) =>
  apiRequest<Paged<GlobalMobileChange>>(
    `${staffPath}/global-mobile-changes/${pageQuery(page)}`,
    { signal },
  );
export const resolveContactReview = (
  id: number,
  reason: string,
  verification_note: string,
) =>
  apiRequest(`${staffPath}/contact-reviews/${id}/resolve/`, {
    method: "POST",
    body: { reason, verification_note, identity_verified: true },
  });
export const resolveRecipientBlock = (
  id: number,
  reason: string,
  verification_note: string,
) =>
  apiRequest(`${staffPath}/recipient-blocks/${id}/resolve/`, {
    method: "POST",
    body: { reason, verification_note, identity_verified: true },
  });
export const updateParentContact = (
  student: number,
  guardian_mobile: string,
  guardian_name: string,
  reason: string,
  verification_note: string,
) =>
  apiRequest(`${staffPath}/students/${student}/contact/`, {
    method: "POST",
    body: {
      guardian_mobile,
      guardian_name,
      reason,
      verification_note,
      identity_verified: true,
    },
  });
export const blockRecipient = (
  student: number,
  mobile: string,
  reason: string,
  verification_note: string,
) =>
  apiRequest(`${staffPath}/students/${student}/recipient-blocks/`, {
    method: "POST",
    body: { mobile, reason, verification_note, identity_verified: true },
  });
export const requestGlobalMobileChange = (
  student: number,
  relation_id: number,
  new_mobile: string,
  reason: string,
  verification_note: string,
) =>
  apiRequest<GlobalMobileChange>(
    `${staffPath}/students/${student}/global-mobile-change/`,
    {
      method: "POST",
      body: {
        relation_id,
        new_mobile,
        reason,
        verification_note,
        identity_verified: true,
      },
    },
  );
