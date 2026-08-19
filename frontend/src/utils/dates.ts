/** تواريخ التقويم المحلية — الخادم يعمل بتاريخ المدرسة لا بـUTC.
 *
 * ‏`toISOString()` يحوّل إلى UTC، فبين منتصف الليل والثالثة فجرًا بتوقيت +03
 * يعطي تاريخ الأمس ويطلب المستخدم يومًا خاطئًا. لذلك تُبنى الأجزاء محليًا.
 */
export function localIsoDate(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
