from django.db import migrations

DIRECT_TABLES = (
    "schools_schoolsettings",
    "academics_academicyear",
    "academics_semester",
    "academics_bellschedule",
    "academics_bellperiod",
    "academics_schoolweekday",
    "students_grade",
    "students_section",
    "students_student",
    "students_studentenrollment",
    "students_studentimportjob",
    "students_studentpurgejob",
    "staff_staffprofile",
    "staff_counselorsectionassignment",
    "staff_staffimportjob",
    "attendance_attendancesession",
    "attendance_attendancedaycontext",
    "attendance_dailyattendancesummary",
    "attendance_attendancemark",
    "attendance_attendancechange",
    "devices_devicebridgeinstallation",
    "devices_attendancedevice",
    "devices_studentdeviceidentity",
    "devices_deviceevent",
    "devices_schoolarrival",
    "devices_schoolarrivalchange",
    "devices_devicerostersyncjob",
    "excuses_absenceexcuse",
    "excuses_absenceexcusetarget",
    "excuses_absenceexcusecoverage",
    "excuses_absenceexcuseattachment",
    "student_warnings_warningrule",
    "student_warnings_studentwarning",
    "student_actions_studentaction",
    "student_leaves_studentleavepermission",
    "student_leaves_studentgaterelease",
    "documents_generateddocument",
    "referrals_studentreferral",
    "referrals_studentreferralcontribution",
    "referrals_studentreferralevent",
    "counseling_counselorcase",
    "counseling_counselorsession",
    "counseling_counselorfollowupplan",
    "counseling_followupgoal",
    "counseling_followupactivity",
    "counseling_teacherfollowuprequest",
    "counseling_teacherfollowupresponse",
    "counseling_counselorcaseevent",
    "subscriptions_schoolsubscription",
    "subscriptions_subscriptionevent",
    "audit_auditlog",
)

DERIVED_TABLES = {
    "students_studentimportrow": (
        "EXISTS (SELECT 1 FROM students_studentimportjob parent "
        "WHERE parent.id = job_id AND parent.school_id = "
        "NULLIF(current_setting('app.current_school_id', true), '')::bigint)"
    ),
    "staff_staffimportrow": (
        "EXISTS (SELECT 1 FROM staff_staffimportjob parent "
        "WHERE parent.id = job_id AND parent.school_id = "
        "NULLIF(current_setting('app.current_school_id', true), '')::bigint)"
    ),
    "devices_devicerostersyncitem": (
        "EXISTS (SELECT 1 FROM devices_devicerostersyncjob parent "
        "WHERE parent.id = job_id AND parent.school_id = "
        "NULLIF(current_setting('app.current_school_id', true), '')::bigint)"
    ),
    "subscriptions_subscriptionentitlement": (
        "EXISTS (SELECT 1 FROM subscriptions_schoolsubscription parent "
        "WHERE parent.id = subscription_id AND parent.school_id = "
        "NULLIF(current_setting('app.current_school_id', true), '')::bigint)"
    ),
}


def _guard(scope: str) -> str:
    return "current_setting('app.rls_bypass', true) = 'on' OR " + scope


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for table in DIRECT_TABLES:
        policy = f"tenant_isolation_{table}"
        scope = (
            "school_id = NULLIF(current_setting('app.current_school_id', true), '')::bigint"
        )
        guard = _guard(scope)
        schema_editor.execute(f"ALTER TABLE {quote(table)} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {quote(policy)} ON {quote(table)} "
            f"USING ({guard}) WITH CHECK ({guard})"
        )
    for table, scope in DERIVED_TABLES.items():
        policy = f"tenant_isolation_{table}"
        guard = _guard(scope)
        schema_editor.execute(f"ALTER TABLE {quote(table)} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {quote(policy)} ON {quote(table)} "
            f"USING ({guard}) WITH CHECK ({guard})"
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for table in (*DIRECT_TABLES, *DERIVED_TABLES):
        policy = f"tenant_isolation_{table}"
        schema_editor.execute(f"DROP POLICY IF EXISTS {quote(policy)} ON {quote(table)}")
        schema_editor.execute(f"ALTER TABLE {quote(table)} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
        ("attendance", "0006_backfill_excused_classification"),
        ("audit", "0002_auditlog_request_id"),
        ("counseling", "0001_initial"),
        ("devices", "0002_devicerostersyncjob_devicerostersyncitem_and_more"),
        ("documents", "0003_alter_generateddocument_snapshot_schema_version"),
        ("excuses", "0001_initial"),
        ("memberships", "0004_schoolmembershipcapability"),
        ("operations", "0001_initial"),
        ("referrals", "0001_initial"),
        ("schools", "0004_school_school_type"),
        ("staff", "0002_counselorsectionassignment"),
        ("student_actions", "0002_alter_studentaction_action_type"),
        ("student_leaves", "0002_gate_release_and_recipient"),
        ("student_warnings", "0002_studentwarning_detail_rows_snapshot"),
        ("students", "0003_section_qr_token"),
        ("subscriptions", "0001_initial"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
