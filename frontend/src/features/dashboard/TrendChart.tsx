import { useId, useState } from "react";

import type { TrendPoint } from "@/features/dashboard/api";
import type { SchoolType } from "@/types/auth";

const WIDTH = 720;
const HEIGHT = 220;
const PAD = { top: 16, bottom: 28, start: 44, end: 12 };

export interface Series {
  key: keyof Omit<TrendPoint, "date">;
  label: string;
  color: string;
}

/** السلاسل المعروضة — كلها **أعداد أيام-طالب**، فمحور واحد لا يخلط عدًا بنسبة (بند 28). */
export const TREND_SERIES: Series[] = [
  { key: "unexcused_full_absence", label: "غياب يوم كامل بدون عذر", color: "#dc2626" },
  { key: "full_absence", label: "غياب يوم كامل (الكل)", color: "#f59e0b" },
  { key: "partial_absence", label: "غياب جزئي", color: "#0ea5e9" },
  { key: "morning_late", label: "تأخر صباحي", color: "#7c3aed" },
  { key: "undetermined", label: "بيانات غير مكتملة", color: "#94a3b8" },
];

const SWATCH_CLASSES: Record<Series["key"], string> = {
  unexcused_full_absence: "bg-red-600",
  full_absence: "bg-amber-500",
  partial_absence: "bg-sky-500",
  morning_late: "bg-violet-600",
  undetermined: "bg-slate-400",
};

function niceMax(value: number): number {
  if (value <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

interface TrendChartProps {
  points: TrendPoint[];
  granularity: "DAY" | "WEEK";
  schoolType: SchoolType;
}

/**
 * مخطط خطي مرسوم يدويًا بـ SVG — لا مكتبة رسم في المشروع، والاعتماد على واحدة
 * لأربع سلاسل لا يبرر حجمها. المحور الزمني يسير **يمينًا ← يسارًا** كاتجاه القراءة،
 * ويرافق المخطط جدول مكافئ لقارئ الشاشة (الرسم وحده ليس بيانًا مقروءًا).
 */
export function TrendChart({ points, granularity, schoolType }: TrendChartProps) {
  const titleId = useId();
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  if (points.length === 0) {
    return (
      <p className="p-6 text-center text-slate-500" data-testid="trend-empty">
        لا توجد بيانات مواظبة في هذه الفترة.
      </p>
    );
  }

  const visible = TREND_SERIES.filter((s) => !hidden.has(s.key));
  const peak = Math.max(
    1,
    ...points.flatMap((point) => visible.map((s) => point[s.key])),
  );
  const max = niceMax(peak);

  const plotWidth = WIDTH - PAD.start - PAD.end;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  // نقطة واحدة: ضعها في المنتصف بدل قسمة على صفر
  const step = points.length > 1 ? plotWidth / (points.length - 1) : 0;
  const xAt = (index: number) =>
    points.length > 1
      ? WIDTH - PAD.end - index * step // الأقدم يمينًا، الأحدث يسارًا (RTL)
      : PAD.start + plotWidth / 2;
  const yAt = (value: number) => PAD.top + plotHeight - (value / max) * plotHeight;

  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round(max * ratio));
  const oldest = points.at(0)?.date ?? "";
  const newest = points.at(-1)?.date ?? "";
  const unitLabel = granularity === "WEEK" ? "أسبوعيًا" : "يوميًا";

  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-labelledby={titleId}
        data-testid="trend-chart"
        data-granularity={granularity}
        data-points={points.length}
      >
        <title id={titleId}>{`اتجاه الغياب ${unitLabel} — أيام-${schoolType === "GIRLS" ? "طالبة" : "طالب"}`}</title>

        {gridValues.map((value) => (
          <g key={value}>
            <line
              x1={PAD.start}
              x2={WIDTH - PAD.end}
              y1={yAt(value)}
              y2={yAt(value)}
              stroke="#e2e8f0"
              strokeWidth={1}
            />
            <text
              x={WIDTH - PAD.end + 4}
              y={yAt(value) + 4}
              fontSize={11}
              fill="#64748b"
              textAnchor="start"
            >
              {value}
            </text>
          </g>
        ))}

        {visible.map((series) => {
          const path = points
            .map((point, index) => `${index === 0 ? "M" : "L"}${xAt(index)},${yAt(point[series.key])}`)
            .join(" ");
          return (
            <g key={series.key} data-testid={`trend-series-${series.key}`}>
              <path d={path} fill="none" stroke={series.color} strokeWidth={2} />
              {points.map((point, index) => (
                <circle
                  key={point.date}
                  cx={xAt(index)}
                  cy={yAt(point[series.key])}
                  r={points.length > 40 ? 1.5 : 3}
                  fill={series.color}
                >
                  <title>{`${point.date} — ${series.label}: ${point[series.key]}`}</title>
                </circle>
              ))}
            </g>
          );
        })}

        <text x={WIDTH - PAD.end} y={HEIGHT - 8} fontSize={11} fill="#64748b" textAnchor="end">
          {oldest}
        </text>
        {newest !== oldest && (
          <text x={PAD.start} y={HEIGHT - 8} fontSize={11} fill="#64748b" textAnchor="start">
            {newest}
          </text>
        )}
      </svg>

      <div className="mt-2 flex flex-wrap gap-2" data-testid="trend-legend">
        {TREND_SERIES.map((series) => {
          const on = !hidden.has(series.key);
          return (
            <button
              key={series.key}
              type="button"
              aria-pressed={on}
              onClick={() =>
                setHidden((prev) => {
                  const next = new Set(prev);
                  if (on) next.add(series.key);
                  else next.delete(series.key);
                  return next;
                })
              }
              className={`flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs ${
                on ? "border-slate-300 text-slate-700" : "border-slate-200 text-slate-400"
              }`}
              data-testid={`trend-toggle-${series.key}`}
            >
              <span
                className={`inline-block size-2.5 rounded-full ${on ? SWATCH_CLASSES[series.key] : "bg-slate-300"}`}
              />
              {series.label}
            </button>
          );
        })}
      </div>

      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-slate-500">
          عرض البيانات كجدول
        </summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="w-full text-xs" data-testid="trend-table">
            <thead className="sticky top-0 bg-slate-50 text-slate-600">
              <tr>
                <th className="p-1.5 text-start">{granularity === "WEEK" ? "بداية الأسبوع" : "اليوم"}</th>
                {TREND_SERIES.map((series) => (
                  <th key={series.key} className="p-1.5 text-start">
                    {series.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.date} className="border-t border-slate-100">
                  <td className="p-1.5 text-slate-600">{point.date}</td>
                  {TREND_SERIES.map((series) => (
                    <td key={series.key} className="p-1.5 text-slate-800">
                      {point[series.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
