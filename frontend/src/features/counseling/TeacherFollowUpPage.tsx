import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import {
  IMPROVEMENT_LABELS,
  type TeacherImprovement,
  getMyFollowUpRequests,
  respondToFollowUp,
} from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";

const IMPROVEMENTS = Object.keys(IMPROVEMENT_LABELS) as TeacherImprovement[];

/** صندوق المعلم — طلباته هو فقط: الطالب والسؤال وردّه.
 *  لا يعرض الحالة ولا جلساتها ولا ردود الزملاء (البنود 68-71). */
export function TeacherFollowUpPage() {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const [observation, setObservation] = useState("");
  const [improvement, setImprovement] = useState<TeacherImprovement>("IMPROVED");
  const [error, setError] = useState<unknown>(null);

  const requests = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-follow-up-requests"),
    queryFn: ({ signal }) => getMyFollowUpRequests(signal),
    enabled: schoolId > 0,
  });

  const submit = async (requestId: number) => {
    try {
      await respondToFollowUp(requestId, {
        observation,
        improvement_status: improvement,
      });
      setOpenId(null);
      setObservation("");
      setError(null);
      await queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "my-follow-up-requests"),
      });
    } catch (err) {
      setError(err);
    }
  };

  if (requests.isPending) return <Spinner />;
  if (requests.isError) return <ErrorState error={requests.error} />;

  const rows = requests.data ?? [];

  return (
    <div className="space-y-4" data-testid="teacher-follow-ups">
      <h1 className="text-2xl font-bold">طلبات المتابعة</h1>
      <p className="text-sm text-slate-600">
        طلبات ملاحظة عن طلابك من المرشد الطلابي — ملاحظتك تصل إليه مباشرة.
      </p>

      {error != null && <ErrorState error={error} />}

      {rows.length === 0 ? (
        <p
          className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm"
          data-testid="no-requests"
        >
          لا توجد طلبات متابعة حاليًا.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
          {rows.map((row) => (
            <li key={row.id} className="space-y-2 p-4" data-testid={`follow-up-${row.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{row.student_name}</span>
                <span className="text-sm text-slate-600">
                  {row.request_type_label} · {row.status_label}
                  {row.due_date ? ` · حتى ${row.due_date}` : ""}
                </span>
              </div>
              <p className="text-sm text-slate-700">{row.question}</p>
              <p className="text-sm text-slate-500">من: {row.requested_by_name ?? "—"}</p>

              {row.response ? (
                <div className="rounded-lg bg-slate-50 p-2 text-sm" data-testid={`my-response-${row.id}`}>
                  <p>{row.response.observation}</p>
                  <p className="text-slate-600">التقييم: {row.response.improvement_status_label}</p>
                </div>
              ) : openId === row.id ? (
                <div className="space-y-2">
                  <textarea
                    data-testid="response-observation"
                    value={observation}
                    onChange={(event) => setObservation(event.target.value)}
                    rows={2}
                    placeholder="ما لاحظته خلال الفترة"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="flex flex-col gap-1 text-sm">
                      التقييم
                      <select
                        data-testid="response-improvement"
                        value={improvement}
                        onChange={(event) =>
                          setImprovement(event.target.value as TeacherImprovement)
                        }
                        className="rounded-lg border border-slate-300 px-3 py-2"
                      >
                        {IMPROVEMENTS.map((value) => (
                          <option key={value} value={value}>
                            {IMPROVEMENT_LABELS[value]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      data-testid="submit-response"
                      disabled={observation.trim().length === 0}
                      onClick={() => submit(row.id)}
                    >
                      إرسال الملاحظة
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  data-testid={`respond-${row.id}`}
                  onClick={() => setOpenId(row.id)}
                  className="text-sm text-blue-700 underline"
                >
                  إضافة ملاحظتي
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
