# Device Bridge API

Authenticated Bridge endpoints use `Authorization: Bearer <bridge-token>`:

- `POST /api/v1/bridge/events/batch/`
- `POST /api/v1/bridge/heartbeat/`
- `GET /api/v1/bridge/devices/`
- `POST /api/v1/bridge/roster/read/`
- `POST /api/v1/bridge/roster/command-result/`

Roster commands are `READ_USERS`, `CREATE_USER`, `UPDATE_USER`, and `DELETE_USER`. Payloads contain only device/job/item/command identifiers, external user ID, display name, and normalized result data. National IDs, guardian fields, device secrets, and biometric templates are excluded.
