"""Recovery contracts expose review metadata and no successful execution contract."""

import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.mark.django_db
def test_recovery_openapi_contracts_are_typed_and_execution_remains_closed():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    contracts = {
        "/api/v1/staff/parents/students/{student_id}/recovery/": ("post",),
        "/api/v1/staff/parents/recovery-cases/": ("get",),
        "/api/v1/staff/parents/recovery-cases/{case_id}/cancel/": ("post",),
        "/api/v1/identity-review/parent-recovery/": ("get",),
        "/api/v1/identity-review/parent-recovery/{case_id}/": ("get",),
        "/api/v1/identity-review/parent-recovery/{case_id}/references/": ("get", "post"),
        "/api/v1/identity-review/parent-recovery/{case_id}/references/{evidence_id}/revoke/": (
            "post",
        ),
        "/api/v1/identity-review/parent-recovery/{case_id}/review/": ("post",),
        "/api/v1/identity-review/parent-recovery/{case_id}/execute/": ("post",),
    }
    operation_ids = []
    for path, methods in contracts.items():
        for method in methods:
            operation = schema["paths"][path][method]
            operation_ids.append(operation["operationId"])
            if path.endswith("/execute/"):
                assert not any(code.startswith("2") for code in operation["responses"])
                typed = operation["responses"]["423"]
            else:
                typed = next(
                    response for code, response in operation["responses"].items()
                    if code.startswith("2")
                )
            assert typed["content"]["application/json"]["schema"]
            if method == "post":
                assert operation["requestBody"]["content"]["application/json"]["schema"]
    assert len(operation_ids) == len(set(operation_ids))
    assert schema["paths"]["/api/v1/identity-review/parent-recovery/"]["get"][
        "operationId"
    ] == "parent_recovery_central_list"
    assert schema["paths"]["/api/v1/identity-review/parent-recovery/{case_id}/"]["get"][
        "operationId"
    ] == "parent_recovery_central_detail"
    properties = schema["components"]["schemas"]["CaseOutput"]["properties"]
    assert {"status", "version", "policy_code", "execution_enabled"} <= properties.keys()
    assert {
        "password", "mobile", "new_mobile", "note", "note_encrypted",
        "account_password_fingerprint", "account_mobile_fingerprint", "source_mobile_hash",
    }.isdisjoint(properties)
