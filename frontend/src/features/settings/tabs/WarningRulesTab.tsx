import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type { RulesMap, WarningLevel, WarningType } from "@/features/warnings/api";
import {
  LEVEL_LABELS,
  LEVELS,
  WARNING_TYPE_LABELS,
  WARNING_TYPE_UNITS,
  getWarningRules,
  patchWarningRules,
} from "@/features/warnings/api";

const TYPES: WarningType[] = ["UNEXCUSED_FULL_DAY_ABSENCE", "MORNING_LATE_OCCURRENCES"];

/** إعدادات الإنذارات (مدير فقط) — الترتيب التصاعدي يتحقق هنا للعرض والـBackend المرجع. */
export function WarningRulesTab() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const canEdit = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const [draft, setDraft] = useState<RulesMap | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const rulesQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "warning-rules"),
    queryFn: ({ signal }) => getWarningRules(signal),
    enabled: schoolId > 0,
  });

  const rules = draft ?? rulesQuery.data ?? null;

  const setLevel = (type: WarningType, level: WarningLevel, value: number) => {
    if (!rules) return;
    setSaved(false);
    setDraft({
      ...rules,
      [type]: { ...rules[type], levels: { ...rules[type].levels, [level]: value } },
    });
  };

  const setEnabled = (type: WarningType, enabled: boolean) => {
    if (!rules) return;
    setSaved(false);
    setDraft({ ...rules, [type]: { ...rules[type], is_enabled: enabled } });
  };

  const orderError = (type: WarningType): string | null => {
    if (!rules) return null;
    const { LEVEL_1: one, LEVEL_2: two, LEVEL_3: three } = rules[type].levels;
    if (!(one < two)) return "يجب أن يكون حد الإنذار الثاني أكبر من الإنذار الأول.";
    if (!(two < three)) return "يجب أن يكون حد الإنذار الثالث أكبر من الإنذار الثاني.";
    return null;
  };

  const blocked = TYPES.some((type) => orderError(type) !== null);

  const save = () => {
    if (!rules || blocked) return;
    setSaving(true);
    setError(null);
    void patchWarningRules(rules)
      .then((next) => {
        queryClient.setQueryData(schoolScopedKey(schoolId, "warning-rules"), next);
        setDraft(null);
        setSaved(true);
      })
      .catch(setError)
      .finally(() => setSaving(false));
  };

  if (rulesQuery.isPending) return <Spinner />;
  if (rulesQuery.isError) return <ErrorState error={rulesQuery.error} />;
  if (!rules) return null;

  return (
    <div className="space-y-4" data-testid="warning-rules-tab">
      <p className="text-sm text-slate-500">
        تحدد المدرسة حدود الإنذارات بنفسها. تغيير الحدود لاحقًا لا يغير أي إنذار صادر —
        كل إنذار يحفظ الحد والقيمة وقت إصداره.
      </p>

      {TYPES.map((type) => {
        const message = orderError(type);
        return (
          <section
            key={type}
            className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            data-testid={`rule-${type}`}
          >
            <label className="flex items-center gap-2 font-bold text-slate-800">
              <input
                type="checkbox"
                checked={rules[type].is_enabled}
                disabled={!canEdit}
                onChange={(e) => setEnabled(type, e.target.checked)}
                data-testid={`enabled-${type}`}
              />
              تفعيل {WARNING_TYPE_LABELS[type]}
            </label>
            <div className="flex flex-wrap gap-3">
              {LEVELS.map((level) => (
                <label key={level} className="text-sm text-slate-600">
                  <span className="mb-1 block">{LEVEL_LABELS[level]}</span>
                  <span className="flex items-center gap-1">
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={rules[type].levels[level]}
                      disabled={!canEdit}
                      onChange={(e) => setLevel(type, level, Number(e.target.value))}
                      className="w-24 rounded-lg border border-slate-300 px-2 py-1.5"
                      aria-label={`${LEVEL_LABELS[level]} — ${WARNING_TYPE_LABELS[type]}`}
                      data-testid={`threshold-${type}-${level}`}
                    />
                    {WARNING_TYPE_UNITS[type]}
                  </span>
                </label>
              ))}
            </div>
            {message && (
              <p className="text-sm text-red-700" role="alert" data-testid={`order-error-${type}`}>
                {message}
              </p>
            )}
          </section>
        );
      })}

      {error != null && <ErrorState error={error} />}
      {saved && (
        <p className="text-sm text-green-700" data-testid="rules-saved">
          حُفظت حدود الإنذارات.
        </p>
      )}
      {canEdit && (
        <Button onClick={save} disabled={saving || blocked} data-testid="save-warning-rules">
          {saving ? "جارٍ الحفظ..." : "حفظ"}
        </Button>
      )}
      {!canEdit && (
        <p className="text-sm text-slate-500">
          إعدادات الإنذارات يعدّلها مدير المدرسة؛ العرض متاح للوكيل.
        </p>
      )}
    </div>
  );
}
