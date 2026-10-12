"""Exercise public HTTPS/CSRF/login using a protected exported environment.

The file is read locally; credentials and response bodies are never printed.
This creates no schools and sends no messages.
"""

import argparse
import http.cookiejar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

parser = argparse.ArgumentParser()
parser.add_argument("--credentials-env", type=Path, required=True)
args = parser.parse_args()
values = {}
for line in args.credentials_env.read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
cookies = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(cookies))


def request(path, body=None):
    headers = {
        "Origin": "https://mowadhabah.com",
        "User-Agent": "Mowadhabah-Migration-Verification/1.0",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        headers["X-CSRFToken"] = next(
            (cookie.value for cookie in cookies if cookie.name == "csrftoken"), ""
        )
    try:
        response = opener.open(
            Request("https://mowadhabah.com/api/v1" + path, data=data, headers=headers), timeout=20
        )
    except HTTPError as error:
        response = error
    assert "application/json" in response.headers.get("Content-Type", ""), (
        f"Non-JSON response for {path}: HTTP {response.status}"
    )
    return response.status, json.loads(response.read())


result = {"base_url": "https://mowadhabah.com", "schools_created": 0}
for path, expected in [
    ("/health/", 200),
    ("/readiness/", 200),
    ("/auth/csrf/", 200),
    ("/auth/me/", 403),
]:
    status, _ = request(path)
    assert status == expected, f"Unexpected status for {path}: {status}"
    result[path] = status
status, plans = request("/auth/registration/plans/")
assert status == 200 and any(plan["can_self_register"] for plan in plans)
result["registration_plans"] = status
status, body = request("/auth/register-school/", {})
assert status == 400 and body.get("code") == "VALIDATION_ERROR"
result["registration_validation"] = status
status, me = request(
    "/auth/login/",
    {"mobile": values["INITIAL_ADMIN_MOBILE"], "password": values["INITIAL_ADMIN_PASSWORD"]},
)
assert status == 200, f"Existing user login failed: HTTP {status}"
result["existing_user_login"] = {
    "status": status,
    "roles": me.get("roles", []),
    "platform_admin": me.get("is_platform_admin"),
}
status, _ = request("/auth/me/")
assert status == 200
result["authenticated_session"] = status
status, _ = request("/auth/logout/", {})
assert status == 200
result["logout"] = status
print(json.dumps(result, sort_keys=True))
