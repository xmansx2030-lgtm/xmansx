"""Read-only preflight for reconciling duplicate student records.

Pass each group as TARGET:SOURCE:SOURCE. No student data is changed.
"""

import json
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count

from common.tenant_rls import tenant_context
from students.models import EnrollmentStatus, Student, StudentEnrollment, StudentImportJob


def _parse_group(value):
    try:
        ids = [int(part) for part in value.split(":")]
    except ValueError as exc:
        raise CommandError("Use TARGET:SOURCE[:SOURCE...] with numeric student IDs.") from exc
    if len(ids) < 2 or any(item <= 0 for item in ids) or len(set(ids)) != len(ids):
        raise CommandError("Each group needs a distinct target and at least one source.")
    return ids


def audit_group(ids, *, school_id=None):
    """Inspect all reverse student relations and database uniqueness collisions."""
    students = list(Student.objects.filter(pk__in=ids).order_by("pk"))
    if len(students) != len(ids):
        raise CommandError(f"Student group {ids}: one or more IDs do not exist.")
    by_id = {student.pk: student for student in students}
    target = by_id[ids[0]]
    if school_id is not None and target.school_id != school_id:
        raise CommandError(f"Student {target.pk} is outside school {school_id}.")
    if any(student.school_id != target.school_id for student in students):
        raise CommandError(f"Student group {ids} crosses schools.")

    latest_import = (
        StudentImportJob.objects.filter(school_id=target.school_id, status="COMPLETED")
        .order_by("-pk")
        .first()
    )
    missing_ids = (
        set((latest_import.summary or {}).get("missing_ids", [])) if latest_import else set()
    )
    names_match = len({" ".join(student.full_name.split()) for student in students}) == 1
    known_guardians = {
        " ".join(student.guardian_name.split())
        for student in students
        if student.guardian_name.strip()
    }
    enrollments = list(
        StudentEnrollment.objects.filter(student_id__in=ids, status=EnrollmentStatus.ACTIVE).values(
            "student_id", "academic_year_id", "grade_id", "section_id"
        )
    )
    enrollment_slices = {
        (row["academic_year_id"], row["grade_id"], row["section_id"]) for row in enrollments
    }

    relations = []
    for relation in Student._meta.related_objects:
        model = relation.related_model
        field = relation.field
        queryset = model._base_manager.filter(**{f"{field.attname}__in": ids})
        counts = dict.fromkeys(ids, 0)
        for student_id, count in (
            queryset.order_by()
            .values(field.attname)
            .annotate(count=Count("pk"))
            .values_list(field.attname, "count")
        ):
            counts[student_id] = count

        collisions = []
        for constraint in model._meta.constraints:
            if field.name not in getattr(constraint, "fields", ()):
                continue
            other_fields = [name for name in constraint.fields if name != field.name]
            if not other_fields:
                continue
            constrained = queryset
            if constraint.condition is not None:
                constrained = constrained.filter(constraint.condition)
            grouped = defaultdict(list)
            for row in constrained.values("pk", field.attname, *other_fields):
                key = tuple(row[name] for name in other_fields)
                grouped[key].append((row["pk"], row[field.attname]))
            for key, records in grouped.items():
                if len(records) > 1:
                    collisions.append(
                        {
                            "constraint": constraint.name,
                            "key": dict(zip(other_fields, key, strict=True)),
                            "records": [{"id": pk, "student_id": sid} for pk, sid in records],
                        }
                    )
        relations.append(
            {
                "model": model._meta.label,
                "counts": counts,
                "collisions": collisions,
            }
        )

    return {
        "school_id": target.school_id,
        "target_id": target.pk,
        "source_ids": ids[1:],
        "students": [
            {
                "id": student.pk,
                "masked_identifier": student.national_id_masked,
                "status": student.status,
            }
            for student in (by_id[item] for item in ids)
        ],
        "identity_checks": {
            "same_name": names_match,
            "same_known_guardian": len(known_guardians) <= 1,
            "same_active_grade_section_year": (
                len(enrollment_slices) == 1 and len(enrollments) == len(ids)
            ),
            "sources_in_latest_import_missing_list": all(item in missing_ids for item in ids[1:]),
            "target_not_in_latest_import_missing_list": ids[0] not in missing_ids,
        },
        "latest_import_job_id": latest_import.pk if latest_import else None,
        "relations": relations,
    }


class Command(BaseCommand):
    help = "Audit confirmed duplicates; --apply reconciles them in one transaction"

    def add_arguments(self, parser):
        parser.add_argument(
            "--group",
            action="append",
            required=True,
            help="TARGET:SOURCE[:SOURCE...] (repeat for each student)",
        )
        parser.add_argument("--school-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-import-job", type=int)

    def handle(self, *args, **options):
        groups = [_parse_group(value) for value in options["group"]]
        flat_ids = [item for group in groups for item in group]
        if len(flat_ids) != len(set(flat_ids)):
            raise CommandError("A student ID may appear in only one group.")
        if options["school_id"] <= 0:
            raise CommandError("School ID must be positive.")
        if options["apply"] and not options["expected_import_job"]:
            raise CommandError("--apply requires --expected-import-job from the latest audit.")
        with tenant_context(school_id=options["school_id"]):
            if options["apply"]:
                from students.services.reconciliation import reconcile_group

                with transaction.atomic():
                    report = [
                        reconcile_group(
                            group,
                            school_id=options["school_id"],
                            expected_import_job_id=options["expected_import_job"],
                        )
                        for group in groups
                    ]
            else:
                report = [audit_group(group, school_id=options["school_id"]) for group in groups]
        self.stdout.write(json.dumps(report, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2))
