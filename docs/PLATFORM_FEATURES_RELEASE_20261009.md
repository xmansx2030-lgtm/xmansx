# Platform feature controls release — 2026-10-09

Based on main f50ac7b. This release integrates the pending school feature controls,
parent approval/email return correction, family search, and counselor family follow-up.
Earlier printing, capacity, school email, and parent activation work is already in main.
Original worktrees and all their local edits remain intact.

Platform school details now control ABSENCE_SMS, PARENT_PORTAL, and BIOMETRIC_DEVICES
independently. Disabled features show an inactive icon and an Arabic subscription
notice; server, background SMS delivery, parent ownership, and bridge ingress enforce
access. Changes require subscription-management capability and create an audit entry.
New schools start with all three features disabled. Existing schools preserve their
contract access until the platform explicitly changes a feature. Plan changes retain
explicit overrides, while subscription lifecycle and role checks still apply.

Parent approval requires a recorded identity proof of at least ten trimmed characters.
School email verification uses the correct user RLS context and preserves a safe return
to the parent-management tab. Family search includes siblings before pagination.
Counselor publications record acknowledgement and action separately without exposing
private case notes or completing the case automatically.

Schema changes: schools.0007_school_feature_access,
subscriptions.0005_alter_planentitlement_key_and_more,
counseling.0003_alter_counselorcaseevent_event_type.
The isolated local/CI seed opts synthetic legacy schools into existing contract access;
production defaults are unchanged.

Release acceptance requires terminal CI (backend, frontend, bridge, eight production
browser shards, five parent TLS journeys, secrets scan), immutable image publication,
both Render services Live at the merged SHA, zero pending migrations, healthy database,
Redis, worker and beat, a verified recent remote backup, and current public PWA assets.
Actual run/deploy evidence is saved separately in tmp/release-result and reported only
after verification. No real email/SMS or school access flag is changed during QA.