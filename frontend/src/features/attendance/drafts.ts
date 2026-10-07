import type { AttendanceSessionData } from "./api";

const PREFIX = "attendance-draft:v1:";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface DraftScope { userId: number; schoolId: number }
interface Draft {
  version: 1;
  updatedAt: string;
  date: string;
  period: number;
  expiresAt: number;
  absentIds: number[];
}

function key(scope: DraftScope, sessionId: number) {
  return `${PREFIX}${scope.userId}:${scope.schoolId}:${sessionId}`;
}

/** Device-only draft: identifiers only, never names, identities or approved marks. */
export function readDraft(scope: DraftScope, session: AttendanceSessionData): number[] | null {
  try {
    const raw = window.localStorage.getItem(key(scope, session.id));
    if (!raw) return null;
    const draft: Partial<Draft> = JSON.parse(raw);
    if (session.status !== "IN_PROGRESS" || draft.version !== 1 ||
        draft.updatedAt !== session.updated_at || draft.date !== session.attendance_date ||
        draft.period !== session.period.sequence || typeof draft.expiresAt !== "number" ||
        draft.expiresAt <= Date.now() || draft.expiresAt > Date.now() + MAX_AGE_MS ||
        !Array.isArray(draft.absentIds) || !draft.absentIds.every((id) => Number.isSafeInteger(id) && id > 0)) {
      removeDraft(scope, session.id);
      return null;
    }
    const rosterIds = new Set(session.roster.map((student) => student.student_id));
    return [...new Set(draft.absentIds)].filter((id) => rosterIds.has(id));
  } catch {
    return null;
  }
}

/** Synchronous on each choice, so immediate reload/navigation cannot outrun a debounce. */
export function writeDraft(scope: DraftScope, session: AttendanceSessionData, absentIds: number[]): boolean {
  if (session.status !== "IN_PROGRESS") return false;
  try {
    const draft: Draft = {
      version: 1, updatedAt: session.updated_at, date: session.attendance_date,
      period: session.period.sequence, expiresAt: Date.now() + MAX_AGE_MS, absentIds,
    };
    window.localStorage.setItem(key(scope, session.id), JSON.stringify(draft));
    return true;
  } catch {
    // Privacy mode, disabled storage and quota errors must never pretend to save.
    removeDraft(scope, session.id);
    return false;
  }
}

export function removeDraft(scope: DraftScope, sessionId: number): void {
  try { window.localStorage.removeItem(key(scope, sessionId)); } catch { /* storage unavailable */ }
}

export function clearAttendanceDrafts(): void {
  try {
    const keys = Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.key(index));
    for (const draftKey of keys) {
      if (draftKey?.startsWith(PREFIX)) window.localStorage.removeItem(draftKey);
    }
  } catch { /* storage unavailable */ }
}
