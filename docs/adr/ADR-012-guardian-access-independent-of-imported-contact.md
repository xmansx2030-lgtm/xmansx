# ADR-012: Guardian Access Is Independent of Imported Contact Data

Status: Accepted for Parent Portal implementation (2026-10-08).

## Context

Noor imports and manual school updates maintain contact information for school
communications. That information can change, be incomplete, or identify another
person. A global account may also be a teacher or have children in other schools.
Treating a matching imported number as a grant would expose student records and
make one school's edit affect unrelated identity or employment.

## Decision

Only an explicitly verified school approval and active `GuardianStudentRelation`
grant family access to a particular student. `Student.guardian_mobile` and
`User.mobile` are separate sources of truth. Imports never create accounts/grants
or modify global login identity. Meaningful changes invalidate affected approvals
atomically, including writes outside services. Independent guardian verification
can be recorded separately from imported-contact bindings.

## Consequences

Registration/activation need dedicated request/token/relation lifecycle records,
school review and PostgreSQL guards. Contact changes fail closed for affected
relations and require explicit reapproval; other children/accounts stay usable.
Existing absence SMS continues using the school contact without requiring a portal
account/relation. Global mobile changes need an independently verified procedure,
not school-contact editing or an activation card.

Implementation contracts, security, tests and rollout are defined once in
[PARENT_PORTAL_ARCHITECTURE.md](../PARENT_PORTAL_ARCHITECTURE.md).
