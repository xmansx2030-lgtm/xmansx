"""بنية أخطاء API الموحدة.

كل خطأ يعود بالشكل: {"code": "...", "message": "...", "details": {...}}
- code: رمز إنجليزي ثابت تعتمد عليه الواجهة.
- message: رسالة عربية واضحة للمستخدم.
- details: تفاصيل حقول التحقق فقط — لا stack traces ولا SQL ولا مسارات داخلية.
"""

import logging

from django.http import HttpRequest, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("xmansx.errors")

_EXCEPTION_MAP: list[tuple[type[Exception], str, str]] = [
    (exceptions.ValidationError, "VALIDATION_ERROR", "البيانات المدخلة غير صحيحة."),
    (exceptions.NotAuthenticated, "NOT_AUTHENTICATED", "يجب تسجيل الدخول أولاً."),
    (exceptions.AuthenticationFailed, "AUTHENTICATION_FAILED", "بيانات الدخول غير صحيحة."),
    (exceptions.PermissionDenied, "PERMISSION_DENIED", "ليست لديك صلاحية لتنفيذ هذا الإجراء."),
    (exceptions.NotFound, "NOT_FOUND", "المورد المطلوب غير موجود."),
    (exceptions.MethodNotAllowed, "METHOD_NOT_ALLOWED", "طريقة الطلب غير مدعومة."),
    (exceptions.Throttled, "RATE_LIMITED", "عدد المحاولات تجاوز الحد المسموح، حاول لاحقاً."),
    (exceptions.ParseError, "PARSE_ERROR", "تعذر قراءة محتوى الطلب."),
]


def _resolve(exc: Exception) -> tuple[str, str]:
    for exc_class, code, message in _EXCEPTION_MAP:
        if isinstance(exc, exc_class):
            return code, message
    return "API_ERROR", "تعذر تنفيذ الطلب."


def api_exception_handler(exc: Exception, context: dict) -> Response | None:
    """يغلف معالج DRF الافتراضي بالبنية الموحدة."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # استثناء غير متوقع → يصعد لـ Django (handler500 يعيد JSON بلا تفاصيل داخلية)
        return None

    code, message = _resolve(exc)
    details = {}
    if isinstance(exc, exceptions.ValidationError):
        details = response.data

    response.data = {"code": code, "message": message, "details": details}
    return response


def handler404(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(
        {"code": "NOT_FOUND", "message": "المورد المطلوب غير موجود.", "details": {}},
        status=status.HTTP_404_NOT_FOUND,
    )


def handler500(request: HttpRequest) -> JsonResponse:
    # التفاصيل الكاملة في السجلات/Sentry فقط — المستخدم يحصل على request_id للدعم
    return JsonResponse(
        {
            "code": "INTERNAL_ERROR",
            "message": "حدث خطأ غير متوقع، حاول مرة أخرى.",
            "details": {"request_id": getattr(request, "request_id", None)},
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
