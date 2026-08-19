import { useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections, getSectionQr, rotateSectionQr } from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";

/** صفحة المدير: توليد/عرض/طباعة/تجديد رمز QR لكل فصل.
 *  الرمز مبهم ولا يمنح صلاحية — التجديد يبطل الملصقات القديمة فورًا. */
export function SectionQrPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [rotating, setRotating] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: activeSchoolId > 0,
  });

  const qrQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "section-qr", selectedId),
    queryFn: ({ signal }) => getSectionQr(selectedId as number, signal),
    enabled: activeSchoolId > 0 && selectedId !== null,
  });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const qrUrl = qrQuery.data
    ? `${window.location.origin}${qrQuery.data.url_path}`
    : null;

  useEffect(() => {
    if (qrUrl && canvasRef.current) {
      void QRCode.toCanvas(canvasRef.current, qrUrl, { width: 280, margin: 2 });
    }
  }, [qrUrl]);

  const handleRotate = async () => {
    if (selectedId === null) return;
    if (!window.confirm("تجديد الرمز يبطل الملصقات المطبوعة القديمة فورًا. المتابعة؟")) return;
    setRotating(true);
    setActionError(null);
    try {
      const info = await rotateSectionQr(selectedId);
      queryClient.setQueryData(
        schoolScopedKey(activeSchoolId, "attendance", "section-qr", selectedId),
        info,
      );
    } catch (error) {
      setActionError(error);
    } finally {
      setRotating(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm print:hidden">
        <h2 className="mb-3 text-lg font-bold text-slate-800">رموز QR للفصول</h2>
        <p className="mb-3 text-sm text-slate-500">
          يعلق الرمز في الفصل ليمسحه المعلم ويفتح التحضير مباشرة. الرمز لا يمنح أي صلاحية —
          الدخول والعضوية مطلوبان دائمًا.
        </p>
        {sectionsQuery.isPending && <Spinner label="جارٍ تحميل الفصول..." />}
        {sectionsQuery.isError && <ErrorState error={sectionsQuery.error} />}
        {sectionsQuery.isSuccess && (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="qr-sections-list">
            {sectionsQuery.data.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(section.id);
                    setActionError(null);
                  }}
                  aria-pressed={selectedId === section.id}
                  className={`w-full rounded-lg border p-3 text-start transition-colors ${
                    selectedId === section.id
                      ? "border-blue-500 bg-blue-50"
                      : "border-slate-200 bg-slate-50 hover:border-blue-300"
                  }`}
                  data-testid={`qr-section-${section.id}`}
                >
                  <span className="block font-medium text-slate-800">{section.name}</span>
                  <span className="block text-xs text-slate-500">{section.grade_name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedId !== null && (
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          {qrQuery.isPending && <Spinner label="جارٍ توليد الرمز..." />}
          {qrQuery.isError && <ErrorState error={qrQuery.error} />}
          {qrQuery.isSuccess && (
            <div className="flex flex-col items-center gap-3 text-center">
              <h3 className="text-xl font-bold text-slate-800" data-testid="qr-section-title">
                {qrQuery.data.section_name} — {qrQuery.data.grade_name}
              </h3>
              <canvas ref={canvasRef} data-testid="qr-canvas" className="rounded-lg" />
              <p className="max-w-xs text-xs text-slate-400 print:text-slate-600">
                امسح الرمز بكاميرا الجهاز لفتح تحضير هذا الفصل.
              </p>
              {actionError != null && <ErrorState error={actionError} />}
              <div className="flex gap-2 print:hidden">
                <Button onClick={() => window.print()}>طباعة</Button>
                <Button
                  variant="danger"
                  onClick={() => void handleRotate()}
                  disabled={rotating}
                  data-testid="rotate-qr"
                >
                  {rotating ? "جارٍ التجديد..." : "تجديد الرمز"}
                </Button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
