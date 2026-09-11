# Morning Attendance

Morning attendance is separate from period absence attendance. `SchoolArrival` stores the first arrival per school/student/date, raw lateness, counted lateness after grace, status, source, and correction history. It is the sole source of student lateness.

No arrival is never interpreted as absence. Device events are deduplicated and unmatched identities can be mapped and reprocessed. Manual arrival/correction is available to manager and vice principal roles. Reports include on-time arrivals, late arrivals, unmatched events, and offline devices; they do not infer absent students from missing biometrics.

Student profiles expose morning late counts/minutes and use dated enrollment for historical display.
