export type PlanDurationUnit = "DAYS" | "MONTHS" | "YEARS";

export function formatPlanDuration(value: number, unit: PlanDurationUnit): string {
  const number = Math.max(1, Math.trunc(value));
  if (unit === "DAYS") {
    if (number === 1) return "يوم واحد";
    if (number === 2) return "يومان";
    if (number >= 3 && number <= 10) return `${number.toLocaleString("ar-SA")} أيام`;
    return `${number.toLocaleString("ar-SA")} يومًا`;
  }
  if (unit === "MONTHS") {
    if (number === 1) return "شهر واحد";
    if (number === 2) return "شهران";
    if (number >= 3 && number <= 10) return `${number.toLocaleString("ar-SA")} أشهر`;
    return `${number.toLocaleString("ar-SA")} شهرًا`;
  }
  if (number === 1) return "سنة واحدة";
  if (number === 2) return "سنتان";
  if (number >= 3 && number <= 10) return `${number.toLocaleString("ar-SA")} سنوات`;
  return `${number.toLocaleString("ar-SA")} سنة`;
}
