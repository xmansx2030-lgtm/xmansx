"""Probe the replacement HTTP stack without creating schools or sending messages."""

import json
import os
import sys
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, "/app")
import django

django.setup()

from django.contrib.auth.hashers import check_password

from accounts.mobile import normalize_mobile
from accounts.models import User

cookies = {}
base_url = os.environ.get("MOWADHABAH_PROBE_BASE_URL", "http://frontend").rstrip("/")
assert base_url in {"http://frontend", "https://mowadhabah.com"}


def request(path, body=None):
    headers = {"Host": "mowadhabah.com", "Origin": "https://mowadhabah.com"}
    if cookies:
        headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        headers["X-CSRFToken"] = cookies.get("csrftoken", "")
    try:
        response = urlopen(
            Request(base_url + "/api/v1" + path, data=data, headers=headers), timeout=15
        )
    except HTTPError as error:
        response = error
    for raw in response.headers.get_all("Set-Cookie", []):
        parsed = SimpleCookie()
        parsed.load(raw)
        cookies.update({name: value.value for name, value in parsed.items()})
    return response.status, json.loads(response.read())


result = {}
for path, expected in [
    ("/health/", 200),
    ("/readiness/", 200),
    ("/auth/csrf/", 200),
    ("/auth/me/", 403),
]:
    status, _ = request(path)
    assert status == expected, f"Unexpected HTTP status for {path}: {status}"
    result[path] = status
status, plans = request("/auth/registration/plans/")
assert status == 200 and any(plan["can_self_register"] for plan in plans), (
    "No self-registration package"
)
result["registration_plans"] = {"status": status, "available": len(plans)}
status, body = request("/auth/register-school/", {})
assert status == 400 and body.get("code") == "VALIDATION_ERROR", (
    "Registration validation/CSRF failed"
)
result["registration_validation"] = {"status": status, "code": body["code"], "schools_created": 0}

mobile = normalize_mobile(os.environ["INITIAL_ADMIN_MOBILE"])
password = os.environ["INITIAL_ADMIN_PASSWORD"]
user = User.objects.filter(mobile=mobile, is_active=True).first()
credentials_match = bool(user and check_password(password, user.password))
result["initial_admin_credentials_match"] = credentials_match
if credentials_match:
    status, me = request("/auth/login/", {"mobile": mobile, "password": password})
    assert status == 200 and me.get("is_platform_admin") == user.is_platform_admin, (
        f"Login failed: status={status}, code={me.get('code')}"
    )
    result["existing_user_login"] = {
        "status": status,
        "platform_admin": me["is_platform_admin"],
        "roles": me.get("roles", []),
    }
    status, me = request("/auth/me/")
    assert status == 200 and me.get("is_platform_admin") == user.is_platform_admin, (
        "Authenticated session failed"
    )
    result["authenticated_session"] = status
    status, _ = request("/auth/logout/", {})
    assert status == 200
    result["logout"] = status
print(json.dumps(result, sort_keys=True))
