export function supportWhatsAppUrl(reason: string, details: readonly string[] = []): string {
  const message = [
    "السلام عليكم ورحمة الله وبركاته،",
    "أود التواصل مع فريق منصة المواظبة.",
    `سبب التواصل: ${reason}`,
    ...details,
    "شكرًا لكم.",
  ].join("\n");

  return `https://wa.me/966537720207?text=${encodeURIComponent(message)}`;
}
