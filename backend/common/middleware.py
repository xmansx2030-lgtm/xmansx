"""Request ID + Structured request logging."""

import logging
import re
import time
import uuid

from django.http import HttpRequest, HttpResponse

from common.logging import request_id_var

logger = logging.getLogger("xmansx.request")

REQUEST_ID_HEADER = "X-Request-ID"
# نقبل معرفًا خارجيًا فقط إذا كان بصيغة آمنة (منع log injection عبر الهيدر)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIDMiddleware:
    """يولد أو يمرر request_id لكل طلب ويعيده في Response header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestLogMiddleware:
    """سجل بنيوي لكل طلب: method, path, status_code, duration_ms.

    لا يسجل headers ولا cookies ولا body.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
