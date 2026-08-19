# Attendance Devices

Phase 8.5 devices are student attendance devices only. `AttendanceDevice` belongs to one school and is reached only through an authenticated local Bridge. Device secrets are encrypted at rest and are not returned to browser APIs. No biometric templates are stored.

The device domain includes health/status, event ingestion, per-device `StudentDeviceIdentity`, morning `SchoolArrival`, and student roster synchronization. Device removal is not SaaS student purge.

Physical vendor adapter status: pending model/protocol verification. The Simulator is the verified development adapter.
