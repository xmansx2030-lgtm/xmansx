import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId, useInvalidateSchoolData } from "@/features/settings/hooks";
import {
  activateStaff,
  addStaffRole,
  getStaff,
  MEMBERSHIP_STATUS_LABELS,
  reinviteStaff,
  removeStaffRole,
  suspendStaff,
  type StaffMember,
} from "@/features/staff/api";
import { ROLE_LABELS } from "@/utils/roles";

const MANAGEABLE_ROLES = ["TEACHER", "COUNSELOR", "VICE_PRINCIPAL", "SCHOOL_MANAGER"];

export function StaffPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const isManager = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const canRead =
    me.data?.roles.some((r) => ["SCHOOL_MANAGER", "VICE_PRINCIPAL"].includes(r)) ?? true;

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [page, setPage] = useState(1);
  const [actionError, setActionError] = useState<string | null>(null);

  const staff = useQuery({
    queryKey: schoolScopedKey(schoolId, "staff", { page, search, roleFilter }),
    queryFn: ({ signal }) =>
      getStaff({ page, search, role: roleFilter }, signal),
    enabled: schoolId > 0 && canRead,
    placeholderData: (previous) => previous,
  });

  const totalPages = staff.data ? Math.max(1, Math.ceil(staff.data.count / 25)) : 1;

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض دليل الموظفين</h2>
      </section>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">موظفو المدرسة</h2>
        {isManager && (
          <Link to="/staff/import">
            <Button>استيراد معلمين</Button>
          </Link>
        )}
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-1">
          <label htmlFor="staff-search" className="text-sm font-medium text-slate-700">
            بحث (اسم / رقم وظيفي / جوال كامل)
          </label>
          <input
            id="staff-search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="staff-role" className="text-sm font-medium text-slate-700">
            الدور
          </label>
          <select
            id="staff-role"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">الكل</option>
            {MANAGEABLE_ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role as keyof typeof ROLE_LABELS]}
              </option>
            ))}
          </select>
        </div>
      </div>

      {actionError && (
        <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </p>
      )}

      {staff.isPending && <Spinner />}
      {staff.isError && <ErrorState error={staff.error} />}

      {staff.data && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <ul className="divide-y divide-slate-100">
            {staff.data.results.map((member) => (
              <StaffRow
                key={member.id}
                member={member}
                isManager={isManager}
                onError={setActionError}
              />
            ))}
            {staff.data.results.length === 0 && (
              <li className="p-6 text-center text-slate-400">لا يوجد موظفون مطابقون.</li>
            )}
          </ul>
          <div className="flex items-center justify-between border-t border-slate-100 p-3 text-sm">
            <span className="text-slate-500">
              الإجمالي: {staff.data.count} — صفحة {page} من {totalPages}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                السابق
              </Button>
              <Button
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                التالي
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StaffRow({
  member,
  isManager,
  onError,
}: {
  member: StaffMember;
  isManager: boolean;
  onError: (message: string | null) => void;
}) {
  const invalidate = useInvalidateSchoolData();
  const [expanded, setExpanded] = useState(false);

  const mutation = useMutation({
    mutationFn: async (action: () => Promise<StaffMember>) => action(),
    onSuccess: () => {
      onError(null);
      void invalidate("staff");
    },
    onError: (e) => onError(e instanceof ApiError ? e.message : "تعذر تنفيذ الإجراء."),
  });

  return (
    <li className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-bold text-slate-800">{member.display_name}</p>
          <p className="text-sm text-slate-500">
            <span dir="ltr">{member.mobile}</span>
            {member.employee_number && <> · رقم وظيفي: {member.employee_number}</>}
            {member.job_title && <> · {member.job_title}</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {member.roles.map((role) => (
            <span
              key={role}
              className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700"
            >
              {ROLE_LABELS[role as keyof typeof ROLE_LABELS] ?? role}
            </span>
          ))}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              member.membership_status === "ACTIVE"
                ? "bg-emerald-100 text-emerald-800"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {MEMBERSHIP_STATUS_LABELS[member.membership_status] ?? member.membership_status}
          </span>
          {isManager && (
            <button
              type="button"
              className="text-sm text-blue-700 underline"
              onClick={() => setExpanded((v) => !v)}
            >
              إدارة
            </button>
          )}
        </div>
      </div>

      {isManager && expanded && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3">
          <span className="text-sm font-medium text-slate-600">الأدوار:</span>
          {MANAGEABLE_ROLES.map((role) => {
            const has = member.roles.includes(role);
            return (
              <label key={role} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={has}
                  disabled={mutation.isPending}
                  onChange={() =>
                    mutation.mutate(() =>
                      has ? removeStaffRole(member.id, role) : addStaffRole(member.id, role),
                    )
                  }
                  className="size-4"
                />
                {ROLE_LABELS[role as keyof typeof ROLE_LABELS]}
              </label>
            );
          })}
          <span className="mx-2 h-5 w-px bg-slate-300" />
          {member.membership_status === "ACTIVE" && (
            <Button
              variant="danger"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(() => suspendStaff(member.id))}
            >
              إيقاف العضوية
            </Button>
          )}
          {member.membership_status === "SUSPENDED" && (
            <Button
              variant="secondary"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(() => activateStaff(member.id))}
            >
              إعادة تفعيل
            </Button>
          )}
          {member.membership_status === "DECLINED" && (
            <Button
              variant="secondary"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(() => reinviteStaff(member.id))}
            >
              إعادة دعوة
            </Button>
          )}
        </div>
      )}
    </li>
  );
}
