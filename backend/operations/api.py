from rest_framework.response import Response

from operations.health import operational_snapshot
from operations.metrics import registry
from subscriptions.permissions import PlatformAPIView


class SystemHealthView(PlatformAPIView):
    def get(self, request):
        return Response({"health": operational_snapshot(), "http": registry.snapshot()})
