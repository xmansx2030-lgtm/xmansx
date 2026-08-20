"""صفحة اشتراك المدرسة — مدير المدرسة يقرأ ولا يغيّر (بند 128)."""

from rest_framework.request import Request
from rest_framework.response import Response

from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from subscriptions.access import subscription_state
from subscriptions.usage import get_school_usage

READ_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


class SchoolSubscriptionView(SchoolScopedAPIView):
    read_roles = READ_ROLES
    write_roles = ()  # لا تعديل من جانب المدرسة في MVP

    def get(self, request: Request) -> Response:
        return Response(
            {
                "subscription": subscription_state(request.school),
                "usage": get_school_usage(request.school),
            }
        )
