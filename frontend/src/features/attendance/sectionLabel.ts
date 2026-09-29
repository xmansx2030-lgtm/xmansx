export function sectionLabel(gradeName: string, sectionName: string, department?: string): string {
  const namedSection = /^\s*فصل\s+/u.test(sectionName) ? sectionName.trim() : `فصل ${sectionName.trim()}`;
  return `${gradeName} / ${namedSection}${department ? ` / ${department}` : ""}`;
}
