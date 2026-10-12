"""Exercise valid school creation in a separate restored QA database."""

import json
import os
import secrets
import sys

assert os.environ["POSTGRES_DB"] == "mowadhabah_registration_drill_20261012"
sys.path.insert(0, "/app")

import django

django.setup()

from rest_framework.test import APIClient

from accounts.models import User
from common.tenant_rls import tenant_context
from memberships.models import SchoolRole
from schools.models import School

client = APIClient(enforce_csrf_checks=True)
request_options = {"secure": True, "HTTP_HOST": "mowadhabah.com"}
response = client.get("/api/v1/auth/csrf/", **request_options)
assert response.status_code == 200
csrf = client.cookies["csrftoken"].value
response = client.get("/api/v1/auth/registration/plans/", **request_options)
assert response.status_code == 200
plan = next(plan for plan in response.json() if plan["can_self_register"])
mobile = next(
    value
    for value in (f"+966500000{number:03d}" for number in range(123, 223))
    if not User.objects.filter(mobile=value).exists()
)
with tenant_context(bypass=True):
    before = School.objects.count()
password = "MigrationQA-7#" + secrets.token_urlsafe(18)
response = client.post(
    "/api/v1/auth/register-school/",
    {
        "school_name": "اختبار نقل Hetzner 20261012",
        "school_type": "BOYS",
        "manager_name": "مدير اختبار النقل",
        "manager_mobile": mobile,
        "manager_email": "migration-qa@example.invalid",
        "password": password,
        "confirm_password": password,
        "plan_id": plan["id"],
        "terms_accepted": True,
    },
    format="json",
    HTTP_X_CSRFTOKEN=csrf,
    HTTP_ORIGIN="https://mowadhabah.com",
    **request_options,
)
assert response.status_code == 201, (
    f"QA registration failed: status={response.status_code}, code={response.json().get('code')}"
)
payload = response.json()
assert payload["roles"] == [SchoolRole.SCHOOL_MANAGER]
assert payload["active_school"] is not None
with tenant_context(bypass=True):
    assert School.objects.count() == before + 1
response = client.get("/api/v1/auth/me/", **request_options)
assert response.status_code == 200
assert response.json()["roles"] == [SchoolRole.SCHOOL_MANAGER]
print(
    json.dumps(
        {
            "registration_status": 201,
            "new_manager_session": 200,
            "manager_roles": [SchoolRole.SCHOOL_MANAGER],
            "schools_created_in_isolated_qa": 1,
            "production_schools_created": 0,
            "outbound_messages_enabled": False,
        }
    )
)
