"""واجهات الأجهزة والصباحي — المدير يدير الأجهزة؛ الوكيل يشارك في الصباحي فقط.

واجهات الجسر بمصادقة رمز مستقلة (لا جلسة/CSRF) — هوية المدرسة من الرمز حصرًا.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AcademicYear, AcademicYearStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.security.identifiers import _fernet
from devices.api.roster_serializers import (
    BridgeRosterCommandSerializer,
    BridgeRosterReadSerializer,
    RosterAnalyzeSerializer,
    RosterSyncItemSerializer,
    RosterSyncJobSerializer,
)
from devices.api.serializers import (
    ArrivalCorrectionSerializer,
    ArrivalSerializer,
    BridgeBatchResultSerializer,
    BridgeBatchSerializer,
    BridgeCreateSerializer,
    BridgeCredentialSerializer,
    BridgeDeviceConfigSerializer,
    BridgeHeartbeatSerializer,
    BridgeSerializer,
    DeviceCreateSerializer,
    DeviceSerializer,
    DeviceUpdateSerializer,
    IdentityMapSerializer,
    IdentitySerializer,
    LateListSerializer,
    ManualArrivalSerializer,
    MorningSummarySerializer,
    StudentLateHistorySerializer,
)
from devices.models import (
    OFFLINE_AFTER_MINUTES,
    AttendanceDevice,
    DeviceBridgeInstallation,
    DeviceRosterSyncAction,
    DeviceRosterSyncItemStatus,
    DeviceRosterSyncJob,
    DeviceRosterSyncStatus,
    DeviceStatus,
    EventProcessingStatus,
    IdentityStatus,
    SchoolArrival,
    StudentDeviceIdentity,
)
from devices.selectors.morning import (
    effective_device_status,
    get_late_list,
    get_morning_summary,
    get_student_late_history,
)
from devices.services import bridge as bridge_service
from devices.services import morning as morning_service
from devices.services import roster as roster_service
from devices.services.ingest import ingest_batch, reprocess_unmatched
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from students.models import Student, StudentImportJob
from subscriptions.entitlements import require_capacity
from subscriptions.models import EntitlementKey
from subscriptions.usage import count_active_devices

MANAGER_ONLY = (SchoolRole.SCHOOL_MANAGER,)
MORNING_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


def _parse_date(request, param="date"):
    from datetime import date as date_cls

    from attendance.services.periods import school_now

    value = request.query_params.get(param)
    if not value:
        return school_now(request.school).date()
    try:
        return date_cls.fromisoformat(value)
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "صيغة التاريخ غير صحيحة (YYYY-MM-DD).") from None


# ---------- الجسور (مدير فقط) ----------


def _bridge_payload(bridge) -> dict:
    from datetime import timedelta

    now = dj_timezone.now()
    online = bool(
        bridge.last_seen_at
        and bridge.last_seen_at >= now - timedelta(minutes=OFFLINE_AFTER_MINUTES)
    )
    return {
        "id": bridge.id,
        "installation_name": bridge.installation_name,
        "status": bridge.status,
        "last_seen_at": bridge.last_seen_at,
        "is_online": online,
    }


class BridgesView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(responses=BridgeSerializer(many=True))
    def get(self, request: Request) -> Response:
        bridges = DeviceBridgeInstallation.objects.filter(school=request.school).order_by("id")
        return Response([_bridge_payload(b) for b in bridges])

    @extend_schema(request=BridgeCreateSerializer, responses=BridgeCredentialSerializer)
    def post(self, request: Request) -> Response:
        serializer = BridgeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bridge, token = bridge_service.create_bridge(
            school=request.school,
            name=serializer.validated_data["name"],
            actor=request.user,
            request=request,
        )
        # الرمز يظهر مرة واحدة — لا يخزن plaintext ولا يعرض ثانية
        return Response(
            {"bridge": _bridge_payload(bridge), "credential": token},
            status=http_status.HTTP_201_CREATED,
        )


class BridgeRotateView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=None, responses=BridgeCredentialSerializer)
    def post(self, request: Request, bridge_id: int) -> Response:
        bridge = get_object_or_404(
            DeviceBridgeInstallation, id=bridge_id, school=request.school
        )
        token = bridge_service.rotate_bridge_credential(
            installation=bridge, actor=request.user, request=request
        )
        return Response({"bridge": _bridge_payload(bridge), "credential": token})


# ---------- الأجهزة (مدير فقط) ----------


def _device_payload(device, unmatched_count: int = 0) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "vendor": device.vendor,
        "model": device.model,
        "serial_number": device.serial_number,
        "connection_type": device.connection_type,
        "local_ip": device.local_ip,
        "local_port": device.local_port,
        "status": effective_device_status(device),
        "last_seen_at": device.last_seen_at,
        "last_successful_sync_at": device.last_successful_sync_at,
        "is_active": device.is_active,
        "unmatched_events": unmatched_count,
        "test_result": device.test_result,
    }


def _apply_device_fields(device, data: dict) -> None:
    for field in (
        "name", "vendor", "model", "serial_number",
        "connection_type", "local_ip", "local_port", "is_active",
    ):
        if field in data:
            setattr(device, field, data[field])
    secret = data.get("connection_secret")
    if secret:
        device.connection_secret_encrypted = _fernet().encrypt(secret.encode()).decode()


class DevicesView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(responses=DeviceSerializer(many=True))
    def get(self, request: Request) -> Response:
        from django.db.models import Count, Q

        devices = (
            AttendanceDevice.objects.filter(school=request.school)
            .annotate(
                unmatched=Count(
                    "events",
                    filter=Q(events__processing_status=EventProcessingStatus.UNMATCHED),
                )
            )
            .order_by("id")
        )
        return Response([_device_payload(d, d.unmatched) for d in devices])

    @extend_schema(request=DeviceCreateSerializer, responses=DeviceSerializer)
    def post(self, request: Request) -> Response:
        serializer = DeviceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # قفل tenant قصير يجعل count + insert قرارًا ذريًا تحت الطلبات المتزامنة.
        from subscriptions.entitlements import lock_school_capacity

        with transaction.atomic():
            lock_school_capacity(request.school)
            require_capacity(
                request.school,
                EntitlementKey.MAX_DEVICES,
                current=count_active_devices(request.school),
            )
            device = AttendanceDevice(school=request.school)
            _apply_device_fields(device, serializer.validated_data)
            device.save()
        record_event(
            AuditAction.DEVICE_CREATED,
            request=request, actor=request.user, school=request.school,
            target_type="AttendanceDevice", target_id=device.id,
            metadata={"name": device.name},  # لا أسرار
        )
        return Response(_device_payload(device), status=http_status.HTTP_201_CREATED)


class DeviceDetailView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=DeviceUpdateSerializer, responses=DeviceSerializer)
    def patch(self, request: Request, device_id: int) -> Response:
        device = get_object_or_404(AttendanceDevice, id=device_id, school=request.school)
        serializer = DeviceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        was_active = device.is_active
        will_activate = (
            not was_active and bool(serializer.validated_data.get("is_active", False))
        )
        from subscriptions.entitlements import lock_school_capacity

        with transaction.atomic():
            if will_activate:
                lock_school_capacity(request.school)
                require_capacity(
                    request.school,
                    EntitlementKey.MAX_DEVICES,
                    current=count_active_devices(request.school),
                )
            _apply_device_fields(device, serializer.validated_data)
            device.save()
        action = (
            AuditAction.DEVICE_DISABLED
            if was_active and not device.is_active
            else AuditAction.DEVICE_UPDATED
        )
        record_event(
            action, request=request, actor=request.user, school=request.school,
            target_type="AttendanceDevice", target_id=device.id,
        )
        return Response(_device_payload(device))


class DeviceTestView(SchoolScopedAPIView):
    """يطلب اختبار اتصال — الجسر يلتقطه في مزامنته التالية ويعيد النتيجة."""

    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=None, responses=DeviceSerializer)
    def post(self, request: Request, device_id: int) -> Response:
        device = get_object_or_404(AttendanceDevice, id=device_id, school=request.school)
        device.test_requested_at = dj_timezone.now()
        device.test_result = None
        device.save(update_fields=["test_requested_at", "test_result", "updated_at"])
        record_event(
            AuditAction.DEVICE_CONNECTION_TESTED,
            request=request, actor=request.user, school=request.school,
            target_type="AttendanceDevice", target_id=device.id,
        )
        return Response(_device_payload(device))


# ---------- المطابقة (مدير فقط) ----------


def _identity_payload(identity) -> dict:
    return {
        "id": identity.id,
        "device_id": identity.device_id,
        "device_name": identity.device.name,
        "external_user_id": identity.external_user_id,
        "display_name": identity.display_name,
        "status": identity.status,
        "student_id": identity.student_id,
        "student_name": identity.student.full_name if identity.student_id else None,
    }


class IdentitiesView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(responses=IdentitySerializer(many=True))
    def get(self, request: Request) -> Response:
        identities = (
            StudentDeviceIdentity.objects.filter(school=request.school)
            .select_related("device", "student")
            .order_by("device_id", "external_user_id")
        )
        status_filter = request.query_params.get("status")
        if status_filter in IdentityStatus.values:
            identities = identities.filter(status=status_filter)
        return Response([_identity_payload(i) for i in identities])


def _roster_job_payload(job) -> dict:
    summary = {
        "student_count": 0,
        "device_user_count": 0,
    }
    if job.roster_version:
        summary["student_count"] = job.matched_count + job.create_count + job.update_count
        summary["device_user_count"] = (
            job.matched_count + job.update_count + job.delete_count + job.conflict_count
        )
    return {
        "id": job.id,
        "device_id": job.device_id,
        "device_name": job.device.name,
        "status": job.status,
        "roster_version": job.roster_version,
        "device_roster_version": job.device_roster_version,
        "matched_count": job.matched_count,
        "create_count": job.create_count,
        "update_count": job.update_count,
        "delete_count": job.delete_count,
        "conflict_count": job.conflict_count,
        **summary,
        "ready_at": job.ready_at,
        "approved_at": job.approved_at,
    }


def _roster_item_payload(item) -> dict:
    return {
        "id": item.id,
        "student_id": item.student_id,
        "student_name": item.student.full_name if item.student_id else None,
        "external_user_id": item.external_user_id,
        "action": item.action,
        "status": item.status,
        "reason": item.reason,
        "error_code": item.error_code,
        "safe_before_snapshot": item.safe_before_snapshot,
        "safe_after_snapshot": item.safe_after_snapshot,
    }


class DeviceRosterAnalyzeView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=RosterAnalyzeSerializer, responses=RosterSyncJobSerializer)
    def post(self, request: Request, device_id: int) -> Response:
        device = get_object_or_404(
            AttendanceDevice, id=device_id, school=request.school, is_active=True
        )
        if DeviceRosterSyncJob.objects.filter(
            device=device,
            status__in=[
                DeviceRosterSyncStatus.ANALYZING,
                DeviceRosterSyncStatus.APPROVED,
                DeviceRosterSyncStatus.RUNNING,
            ],
        ).exists():
            raise ApiError(
                "DEVICE_ROSTER_SYNC_ALREADY_RUNNING",
                "توجد مزامنة قائمة لهذا الجهاز.",
                status_code=409,
            )
        year = AcademicYear.objects.filter(
            school=request.school, status=AcademicYearStatus.ACTIVE
        ).first()
        import_job = (
            StudentImportJob.objects.filter(school=request.school, status="COMPLETED")
            .order_by("-id")
            .first()
        )
        job = DeviceRosterSyncJob.objects.create(
            school=request.school,
            device=device,
            created_by_membership=request.membership,
            source_academic_year=year,
            source_student_import=import_job,
            read_requested_at=dj_timezone.now(),
        )
        return Response(_roster_job_payload(job), status=http_status.HTTP_202_ACCEPTED)


class DeviceRosterJobView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
    write_roles = MANAGER_ONLY

    @extend_schema(responses=RosterSyncJobSerializer)
    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(
            DeviceRosterSyncJob.objects.select_related("device"),
            id=job_id,
            school=request.school,
        )
        return Response(_roster_job_payload(job))


class DeviceRosterItemsView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
    write_roles = MANAGER_ONLY

    @extend_schema(responses=RosterSyncItemSerializer(many=True))
    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(DeviceRosterSyncJob, id=job_id, school=request.school)
        items = job.items.select_related("student").order_by("action", "id")
        action = request.query_params.get("action")
        if action in DeviceRosterSyncAction.values:
            items = items.filter(action=action)
        return Response([_roster_item_payload(item) for item in items])


class DeviceRosterApproveView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=None, responses=RosterSyncJobSerializer)
    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(
            DeviceRosterSyncJob.objects.select_related("device"),
            id=job_id,
            school=request.school,
        )
        try:
            job = roster_service.approve_job(job=job, membership=request.membership)
        except ValueError as exc:
            code = str(exc)
            messages = {
                "DEVICE_ROSTER_SYNC_NOT_READY": "المزامنة ليست جاهزة للاعتماد.",
                "DEVICE_ROSTER_PREVIEW_STALE": "تغيرت بيانات الطلاب منذ إنشاء المعاينة. أعد الفحص.",
            }
            raise ApiError(
                code, messages.get(code, "تعذر اعتماد المزامنة."), status_code=409
            ) from None
        return Response(_roster_job_payload(job))


class DeviceRosterRetryView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=None, responses=RosterSyncJobSerializer)
    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(
            DeviceRosterSyncJob.objects.select_related("device"),
            id=job_id,
            school=request.school,
        )
        if job.status != DeviceRosterSyncStatus.PARTIALLY_FAILED:
            raise ApiError(
                "DEVICE_ROSTER_SYNC_NOT_RETRYABLE",
                "لا توجد عناصر فاشلة قابلة للإعادة.",
                409,
            )
        job.items.filter(status=DeviceRosterSyncItemStatus.FAILED_RETRYABLE).update(
            status=DeviceRosterSyncItemStatus.PENDING,
            error_code="",
            updated_at=dj_timezone.now(),
        )
        job.status = DeviceRosterSyncStatus.APPROVED
        job.save(update_fields=["status", "updated_at"])
        return Response(_roster_job_payload(job))


class IdentityMapView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=IdentityMapSerializer, responses=IdentitySerializer)
    def post(self, request: Request, identity_id: int) -> Response:
        identity = get_object_or_404(
            StudentDeviceIdentity.objects.select_related("device"),
            id=identity_id,
            school=request.school,
        )
        serializer = IdentityMapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = get_object_or_404(
            Student, id=serializer.validated_data["student_id"], school=request.school
        )
        identity.student = student
        identity.status = IdentityStatus.MATCHED
        identity.mapped_at = dj_timezone.now()
        identity.mapped_by_membership = request.membership
        identity.save()
        reprocessed = reprocess_unmatched(identity=identity)
        record_event(
            AuditAction.DEVICE_USER_MAPPED,
            request=request, actor=request.user, school=request.school,
            target_type="StudentDeviceIdentity", target_id=identity.id,
            metadata={"reprocessed_events": reprocessed},  # لا اسم/هوية
        )
        return Response(_identity_payload(identity))


class IdentityUnmapView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=None, responses=IdentitySerializer)
    def post(self, request: Request, identity_id: int) -> Response:
        identity = get_object_or_404(
            StudentDeviceIdentity.objects.select_related("device"),
            id=identity_id,
            school=request.school,
        )
        identity.student = None
        identity.status = IdentityStatus.UNMATCHED
        identity.mapped_at = None
        identity.mapped_by_membership = None
        identity.save()
        record_event(
            AuditAction.DEVICE_USER_UNMAPPED,
            request=request, actor=request.user, school=request.school,
            target_type="StudentDeviceIdentity", target_id=identity.id,
        )
        return Response(_identity_payload(identity))


# ---------- الحضور الصباحي (مدير + وكيل) ----------


class MorningSummaryView(SchoolScopedAPIView):
    read_roles = MORNING_ROLES
    write_roles = MORNING_ROLES

    @extend_schema(responses=MorningSummarySerializer)
    def get(self, request: Request) -> Response:
        return Response(
            get_morning_summary(school=request.school, attendance_date=_parse_date(request))
        )


class MorningLateListView(SchoolScopedAPIView):
    read_roles = MORNING_ROLES
    write_roles = MORNING_ROLES

    @extend_schema(responses=LateListSerializer)
    def get(self, request: Request) -> Response:
        def _int(name):
            value = request.query_params.get(name)
            try:
                return int(value) if value else None
            except ValueError:
                raise ApiError("VALIDATION_ERROR", "قيمة رقمية غير صحيحة.") from None

        return Response(
            get_late_list(
                school=request.school,
                attendance_date=_parse_date(request),
                grade_id=_int("grade"),
                section_id=_int("section"),
                search=request.query_params.get("search", ""),
                page=_int("page") or 1,
                page_size=_int("page_size") or 25,
            )
        )


class StudentLateHistoryView(SchoolScopedAPIView):
    read_roles = MORNING_ROLES
    write_roles = MORNING_ROLES

    @extend_schema(responses=StudentLateHistorySerializer)
    def get(self, request: Request, student_id: int) -> Response:
        from datetime import date as date_cls

        student = get_object_or_404(Student, id=student_id, school=request.school)
        try:
            date_from = date_cls.fromisoformat(request.query_params.get("from", ""))
            date_to = date_cls.fromisoformat(request.query_params.get("to", ""))
        except ValueError:
            raise ApiError(
                "VALIDATION_ERROR", "حدد الفترة بصيغة YYYY-MM-DD."
            ) from None
        return Response(
            get_student_late_history(
                school=request.school, student=student, date_from=date_from, date_to=date_to
            )
        )


def _arrival_payload(arrival) -> dict:
    from zoneinfo import ZoneInfo

    from schools.services.settings import get_or_create_settings

    tz = ZoneInfo(get_or_create_settings(school=arrival.school).timezone)
    return {
        "id": arrival.id,
        "student_id": arrival.student_id,
        "attendance_date": arrival.attendance_date,
        "arrival_time": arrival.first_arrival_at.astimezone(tz).strftime("%H:%M"),
        "status": arrival.status,
        "raw_late_minutes": arrival.raw_late_minutes,
        "counted_late_minutes": arrival.counted_late_minutes,
        "source": arrival.source,
    }


class ManualArrivalView(SchoolScopedAPIView):
    read_roles = MORNING_ROLES
    write_roles = MORNING_ROLES

    @extend_schema(request=ManualArrivalSerializer, responses=ArrivalSerializer)
    def post(self, request: Request) -> Response:
        serializer = ManualArrivalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = get_object_or_404(
            Student, id=data["student_id"], school=request.school
        )
        arrival = morning_service.create_manual_arrival(
            school=request.school,
            membership=request.membership,
            student=student,
            attendance_date=data["date"],
            arrival_time=data["arrival_time"],
            reason=data["reason"],
            request=request,
        )
        return Response(_arrival_payload(arrival), status=http_status.HTTP_201_CREATED)


class ArrivalCorrectView(SchoolScopedAPIView):
    read_roles = MORNING_ROLES
    write_roles = MORNING_ROLES

    @extend_schema(request=ArrivalCorrectionSerializer, responses=ArrivalSerializer)
    def post(self, request: Request, arrival_id: int) -> Response:
        arrival = get_object_or_404(SchoolArrival, id=arrival_id, school=request.school)
        serializer = ArrivalCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        arrival = morning_service.correct_arrival(
            arrival=arrival,
            membership=request.membership,
            new_time=serializer.validated_data["arrival_time"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(_arrival_payload(arrival))


# ---------- واجهات الجسر (رمز اعتماد — لا جلسة ولا CSRF) ----------


class BridgeAPIView(APIView):
    """أساس واجهات الجسر: مصادقة بالرمز، وهوية المدرسة منه حصرًا."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get_bridge(self, request: Request):
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip() if header else None
        return bridge_service.authenticate_bridge(token)


class BridgeEventsBatchView(BridgeAPIView):
    @extend_schema(request=BridgeBatchSerializer, responses=BridgeBatchResultSerializer)
    def post(self, request: Request) -> Response:
        bridge = self.get_bridge(request)
        serializer = BridgeBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = ingest_batch(bridge=bridge, events=serializer.validated_data["events"])
        return Response({"results": results})


class BridgeHeartbeatView(BridgeAPIView):
    @extend_schema(
        request=BridgeHeartbeatSerializer,
        responses=BridgeDeviceConfigSerializer(many=True),
    )
    def post(self, request: Request) -> Response:
        bridge = self.get_bridge(request)
        serializer = BridgeHeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = dj_timezone.now()
        devices = {
            d.id: d for d in AttendanceDevice.objects.filter(school=bridge.school)
        }
        for report in serializer.validated_data.get("devices", []):
            device = devices.get(report["device_id"])
            if device is None:
                continue  # جهاز مدرسة أخرى/غير موجود — يتجاهل بصمت (لا استكشاف)
            device.last_seen_at = now
            device.status = (
                DeviceStatus.ONLINE if report["reachable"] else DeviceStatus.DEGRADED
            )
            update_fields = ["last_seen_at", "status", "updated_at"]
            if report.get("test_result") is not None and device.test_requested_at:
                device.test_result = report["test_result"]
                device.test_requested_at = None
                update_fields += ["test_result", "test_requested_at"]
            device.save(update_fields=update_fields)
        return Response(
            _bridge_device_configs(
                bridge,
                include_commands=not bool(serializer.validated_data.get("devices")),
            )
        )


class BridgeDevicesView(BridgeAPIView):
    @extend_schema(responses=BridgeDeviceConfigSerializer(many=True))
    def get(self, request: Request) -> Response:
        bridge = self.get_bridge(request)
        return Response(_bridge_device_configs(bridge))


class BridgeRosterReadView(BridgeAPIView):
    @extend_schema(request=BridgeRosterReadSerializer, responses=RosterSyncJobSerializer)
    def post(self, request: Request) -> Response:
        bridge = self.get_bridge(request)
        serializer = BridgeRosterReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = get_object_or_404(
            DeviceRosterSyncJob.objects.select_related("device"),
            id=data["job_id"],
            device_id=data["device_id"],
            school=bridge.school,
            status__in=[
                DeviceRosterSyncStatus.ANALYZING,
                DeviceRosterSyncStatus.APPROVED,
                DeviceRosterSyncStatus.RUNNING,
            ],
        )
        if job.status == DeviceRosterSyncStatus.APPROVED:
            if data.get("device_roster_version") != job.device_roster_version:
                job.status = DeviceRosterSyncStatus.STALE
                job.save(update_fields=["status", "updated_at"])
                raise ApiError(
                    "DEVICE_ROSTER_PREVIEW_STALE",
                    "تغيرت قائمة مستخدمي الجهاز منذ إنشاء المعاينة. أعد الفحص.",
                    status_code=409,
                )
            job.status = DeviceRosterSyncStatus.RUNNING
            job.save(update_fields=["status", "updated_at"])
            return Response(_roster_job_payload(job))
        if job.status == DeviceRosterSyncStatus.RUNNING:
            result = roster_service.compare_device_roster(
                school=bridge.school, device=job.device, device_users=data["users"]
            )
            if all(
                result["summary"][key] == 0
                for key in ("create_count", "update_count", "delete_count", "conflict_count")
            ):
                job.status = DeviceRosterSyncStatus.COMPLETED
                job.completed_at = dj_timezone.now()
                job.save(update_fields=["status", "completed_at", "updated_at"])
            return Response(_roster_job_payload(job))
        job = roster_service.save_analysis(job=job, device_users=data["users"])
        return Response(_roster_job_payload(job))


class BridgeRosterCommandResultView(BridgeAPIView):
    @extend_schema(request=BridgeRosterCommandSerializer, responses=RosterSyncJobSerializer)
    def post(self, request: Request) -> Response:
        bridge = self.get_bridge(request)
        serializer = BridgeRosterCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = get_object_or_404(
            DeviceRosterSyncJob.objects.select_related("device"),
            id=data["job_id"],
            device_id__in=AttendanceDevice.objects.filter(school=bridge.school).values("id"),
            status__in=[DeviceRosterSyncStatus.APPROVED, DeviceRosterSyncStatus.RUNNING],
        )
        item = get_object_or_404(job.items, id=data["item_id"], command_id=data["command_id"])
        if item.status in [
            DeviceRosterSyncItemStatus.SUCCEEDED,
            DeviceRosterSyncItemStatus.FAILED_FINAL,
        ]:
            return Response(_roster_job_payload(job))
        item.status = data["result"]
        item.error_code = data.get("error_code", "")
        item.attempts += 1
        item.save(update_fields=["status", "error_code", "attempts", "updated_at"])
        if item.status == DeviceRosterSyncItemStatus.SUCCEEDED and item.student_id:
            if item.action == DeviceRosterSyncAction.DELETE:
                StudentDeviceIdentity.objects.filter(
                    device=job.device, external_user_id=item.external_user_id
                ).update(
                    status=IdentityStatus.MATCHED,
                    display_name=item.safe_before_snapshot.get("display_name", ""),
                )
            else:
                StudentDeviceIdentity.objects.update_or_create(
                    device=job.device,
                    external_user_id=item.external_user_id,
                    defaults={
                        "school": job.school,
                        "student_id": item.student_id,
                        "display_name": item.safe_after_snapshot.get("display_name", ""),
                        "status": IdentityStatus.MATCHED,
                    },
                )
        has_open_items = job.items.filter(
            status__in=[
                DeviceRosterSyncItemStatus.PENDING,
                DeviceRosterSyncItemStatus.RUNNING,
            ]
        ).exists()
        if not has_open_items:
            if job.items.filter(status=DeviceRosterSyncItemStatus.FAILED_FINAL).exists():
                job.status = DeviceRosterSyncStatus.PARTIALLY_FAILED
            elif job.items.filter(status=DeviceRosterSyncItemStatus.FAILED_RETRYABLE).exists():
                job.status = DeviceRosterSyncStatus.PARTIALLY_FAILED
            else:
                job.status = DeviceRosterSyncStatus.RUNNING
        else:
            job.status = DeviceRosterSyncStatus.RUNNING
        job.started_at = job.started_at or dj_timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])
        return Response(_roster_job_payload(job))


def _bridge_device_configs(bridge, *, include_commands: bool = True) -> list[dict]:
    configs = []
    for device in AttendanceDevice.objects.filter(school=bridge.school, is_active=True):
        secret = ""
        if device.connection_secret_encrypted:
            secret = _fernet().decrypt(device.connection_secret_encrypted.encode()).decode()
        read_job = DeviceRosterSyncJob.objects.filter(
            device=device,
            status__in=[
                DeviceRosterSyncStatus.ANALYZING,
                DeviceRosterSyncStatus.APPROVED,
                DeviceRosterSyncStatus.RUNNING,
            ],
        ).order_by("id").first()
        commands = []
        command_job = DeviceRosterSyncJob.objects.filter(
            device=device,
            status=DeviceRosterSyncStatus.RUNNING,
        ).order_by("id").first()
        if command_job and include_commands:
            pending_items = command_job.items.filter(
                action__in=[
                    DeviceRosterSyncAction.CREATE,
                    DeviceRosterSyncAction.UPDATE,
                    DeviceRosterSyncAction.DELETE,
                ],
                status=DeviceRosterSyncItemStatus.PENDING,
            ).select_related("student")[:100]
            for item in pending_items:
                commands.append(roster_service.command_payload(item))
                item.status = DeviceRosterSyncItemStatus.RUNNING
                item.save(update_fields=["status", "updated_at"])
            if commands and command_job.status == DeviceRosterSyncStatus.APPROVED:
                command_job.status = DeviceRosterSyncStatus.RUNNING
                command_job.started_at = dj_timezone.now()
                command_job.save(update_fields=["status", "started_at", "updated_at"])
        configs.append(
            {
                "id": device.id,
                "name": device.name,
                "vendor": device.vendor,
                "connection_type": device.connection_type,
                "local_ip": device.local_ip,
                "local_port": device.local_port,
                "connection_secret": secret,
                "test_requested": device.test_requested_at is not None,
                "roster_read_job_id": read_job.id if read_job else None,
                "roster_commands": commands,
            }
        )
    return configs
