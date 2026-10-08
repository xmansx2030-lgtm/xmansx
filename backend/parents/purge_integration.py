"""Purge family records before their student and protected administrative sources."""


def collect_parent_request_files(student):
    from parents.models import ParentExcuseAttachment

    return [
        attachment.file
        for attachment in ParentExcuseAttachment.objects.filter(
            parent_request__student=student,
        )
        if attachment.file
    ]


def register_purge_steps():
    from parents import models
    from students.services import purge

    steps = [
        (
            "قرارات مراجعة استعادة الحساب",
            lambda ids: models.RecoveryReviewDecision.objects.filter(case__student_id__in=ids),
        ),
        (
            "مراجع استعادة الحساب",
            lambda ids: models.RecoveryEvidenceReference.objects.filter(case__student_id__in=ids),
        ),
        (
            "قضايا استعادة الحساب",
            lambda ids: models.GlobalAccountRecoveryCase.objects.filter(student_id__in=ids),
        ),
        (
            "تنبيهات أولياء الأمور",
            lambda ids: models.ParentNotification.objects.filter(relation__student_id__in=ids),
        ),
        (
            "تأكيد اطلاع الإنذارات",
            lambda ids: models.WarningAcknowledgement.objects.filter(warning__student_id__in=ids),
        ),
        (
            "تأكيد اطلاع الأسرة",
            lambda ids: models.FamilyPublicationAcknowledgement.objects.filter(
                publication__student_id__in=ids
            ),
        ),
        (
            "محتوى الأسرة المنشور",
            lambda ids: models.FamilyPublication.objects.filter(student_id__in=ids),
        ),
        (
            "مرفقات طلبات الأسرة",
            lambda ids: models.ParentExcuseAttachment.objects.filter(
                parent_request__student_id__in=ids
            ),
        ),
        (
            "طلبات أعذار الأسرة",
            lambda ids: models.ParentExcuseRequest.objects.filter(student_id__in=ids),
        ),
        (
            "طلبات تصحيح الأسرة",
            lambda ids: models.AttendanceCorrectionRequest.objects.filter(student_id__in=ids),
        ),
        (
            "تفعيل أولياء الأمور",
            lambda ids: models.GuardianActivation.objects.filter(student_id__in=ids),
        ),
        (
            "تسجيل أولياء الأمور",
            lambda ids: models.GuardianRegistrationRequest.objects.filter(student_id__in=ids),
        ),
        (
            "مراجعات تواصل الأسرة",
            lambda ids: models.GuardianContactReview.objects.filter(student_id__in=ids),
        ),
        (
            "طلبات تغيير جوال الأسرة",
            lambda ids: models.GlobalMobileChangeRequest.objects.filter(student_id__in=ids),
        ),
        (
            "حماية مستلمي الرسائل",
            lambda ids: models.RecipientContactBlock.objects.filter(student_id__in=ids),
        ),
        (
            "علاقات أولياء الأمور",
            lambda ids: models.GuardianStudentRelation.objects.filter(student_id__in=ids),
        ),
    ]
    existing = {label for label, _ in purge.PURGE_STEPS}
    for label, queryset in reversed(steps):
        if label not in existing:
            purge.PURGE_STEPS.insert(0, (label, queryset))
    if not any(
        collector.__name__ == collect_parent_request_files.__name__
        for collector in purge.PURGE_STORAGE_COLLECTORS
    ):
        purge.PURGE_STORAGE_COLLECTORS.append(collect_parent_request_files)
