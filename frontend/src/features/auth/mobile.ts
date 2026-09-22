const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const MOBILE_SEPARATORS_RE = /[\s\-().]/g;

export function toLatinDigits(value: string): string {
  return [...value].map((char) => {
    const index = ARABIC_DIGITS.indexOf(char);
    return index === -1 ? char : String(index);
  }).join("");
}

export function toCanonicalMobile(value: string): string | null {
  const compact = toLatinDigits(value.trim()).replace(MOBILE_SEPARATORS_RE, "");
  const digits = compact.startsWith("+")
    ? compact.slice(1)
    : compact.startsWith("00")
      ? compact.slice(2)
      : compact;

  if (!/^\d+$/.test(digits)) return null;

  const national = digits.startsWith("966")
    ? digits.slice(3)
    : digits.startsWith("05")
      ? digits.slice(1)
      : digits.startsWith("5")
        ? digits
        : null;

  return national && /^5\d{8}$/.test(national) ? `+966${national}` : null;
}
