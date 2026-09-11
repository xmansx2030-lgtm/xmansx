from time import perf_counter

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from schools.models import School
from students.models import Student
from subscriptions.api.views import _platform_school_queryset, _school_row
from subscriptions.entitlements import get_limit, has_entitlement
from subscriptions.models import (
    EntitlementKey,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionEntitlement,
    SubscriptionStatus,
)
from subscriptions.usage import get_school_usage


class Command(BaseCommand):
    help = "Benchmark Phase 16 usage and platform-school list query scaling."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._run_usage_benchmarks()
            self._run_platform_list_benchmarks()
            transaction.set_rollback(True)

        self.stdout.write("Benchmark fixtures rolled back.")

    def _run_usage_benchmarks(self):
        plan = SaaSPlan.objects.create(
            code="phase16-benchmark-usage",
            name_ar="Phase 16 usage benchmark",
        )
        now = timezone.now()

        for size in (500, 1000, 3000, 5000):
            school = School.objects.create(
                name=f"Phase 16 usage {size}",
                slug=f"phase16-benchmark-usage-{size}",
            )
            subscription = SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                starts_at=now,
                ends_at=now + timezone.timedelta(days=365),
            )
            SubscriptionEntitlement.objects.bulk_create(
                [
                    SubscriptionEntitlement(
                        subscription=subscription,
                        key=EntitlementKey.MAX_STUDENTS,
                        numeric_value=10_000,
                    ),
                    SubscriptionEntitlement(
                        subscription=subscription,
                        key=EntitlementKey.MAX_STAFF,
                        numeric_value=100,
                    ),
                    SubscriptionEntitlement(
                        subscription=subscription,
                        key=EntitlementKey.MAX_DEVICES,
                        numeric_value=100,
                    ),
                    SubscriptionEntitlement(
                        subscription=subscription,
                        key=EntitlementKey.MAX_STORAGE_GB,
                        numeric_value=100,
                    ),
                    SubscriptionEntitlement(
                        subscription=subscription,
                        key=EntitlementKey.COUNSELING,
                        is_enabled=True,
                    ),
                ]
            )
            Student.objects.bulk_create(
                [
                    Student(
                        school=school,
                        national_id_encrypted=f"benchmark-{size}-{index}",
                        national_id_lookup_hash=f"benchmark-{size}-{index:08d}",
                        national_id_masked="******0000",
                        student_number=f"BENCH-{size}-{index}",
                        full_name=f"Benchmark student {index}",
                    )
                    for index in range(size)
                ],
                batch_size=1000,
            )

            cache.clear()
            with CaptureQueriesContext(connection) as queries:
                started = perf_counter()
                usage = get_school_usage(school)
                duration_ms = (perf_counter() - started) * 1000
            self.stdout.write(
                f"usage students={size} duration_ms={duration_ms:.2f} "
                f"queries={len(queries)} measured={usage['students']['used']}"
            )

            if size == 5000:
                get_limit(school, EntitlementKey.MAX_STUDENTS)
                with CaptureQueriesContext(connection) as queries:
                    started = perf_counter()
                    for _ in range(1000):
                        get_limit(school, EntitlementKey.MAX_STUDENTS)
                        has_entitlement(school, EntitlementKey.COUNSELING)
                    duration_ms = (perf_counter() - started) * 1000
                self.stdout.write(
                    f"entitlement_lookups=2000 duration_ms={duration_ms:.2f} "
                    f"queries={len(queries)}"
                )

    def _run_platform_list_benchmarks(self):
        plan = SaaSPlan.objects.create(
            code="phase16-benchmark-list",
            name_ar="Phase 16 list benchmark",
        )
        now = timezone.now()
        schools = School.objects.bulk_create(
            [
                School(
                    name=f"Phase 16 list {index:04d}",
                    slug=f"phase16-benchmark-list-{index:04d}",
                )
                for index in range(1000)
            ],
            batch_size=1000,
        )
        subscriptions = SchoolSubscription.objects.bulk_create(
            [
                SchoolSubscription(
                    school=school,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    starts_at=now,
                    ends_at=now + timezone.timedelta(days=365),
                )
                for school in schools
            ],
            batch_size=1000,
        )
        SubscriptionEntitlement.objects.bulk_create(
            [
                SubscriptionEntitlement(
                    subscription=subscription,
                    key=EntitlementKey.MAX_STUDENTS,
                    numeric_value=1000,
                )
                for subscription in subscriptions
            ],
            batch_size=1000,
        )

        for total_schools in (100, 500, 1000):
            queryset = _platform_school_queryset().filter(
                slug__gte="phase16-benchmark-list-0000",
                slug__lt=f"phase16-benchmark-list-{total_schools:04d}",
            )
            with CaptureQueriesContext(connection) as queries:
                started = perf_counter()
                measured_total = queryset.count()
                rows = [_school_row(school) for school in queryset[:100]]
                duration_ms = (perf_counter() - started) * 1000
            self.stdout.write(
                f"platform_total={total_schools} page_size=100 "
                f"duration_ms={duration_ms:.2f} queries={len(queries)} "
                f"measured_total={measured_total} serialized={len(rows)}"
            )
