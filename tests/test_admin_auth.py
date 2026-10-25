from datetime import date
from decimal import Decimal
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import pytest

from app import main


client = TestClient(main.app)


def test_password_hash_verifies_without_storing_plaintext():
    password = "correct horse battery staple"
    password_hash = main.hash_password(password)

    assert password not in password_hash
    assert main.verify_password(password, password_hash)
    assert not main.verify_password("incorrect password", password_hash)


def test_signed_session_rejects_tampering_and_expiration(monkeypatch):
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "session-secret-value-with-more-than-32-characters")
    clock = {"now": 1_000.0}
    monkeypatch.setattr(main.time, "time", lambda: clock["now"])
    token = main.encode_session("reviewer-one")

    assert main.decode_session(token) == "reviewer-one"
    assert main.decode_session(token + "x") is None
    clock["now"] += main.SESSION_MAX_AGE
    assert main.decode_session(token) is None
    assert main.decode_session("not-a-session") is None


def test_login_issues_signed_http_only_cookie(monkeypatch):
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "session-secret-value-with-more-than-32-characters")
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", "false")
    cursor = MagicMock()
    cursor.fetchone.return_value = {"password_hash": main.hash_password("correct horse battery staple")}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)

    response = client.post(
        "/admin/login",
        json={"username": "reviewer-one", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200
    assert response.json() == {"username": "reviewer-one"}
    assert response.cookies.get(main.SESSION_COOKIE)
    assert "httponly" in response.headers["set-cookie"].lower()


def test_mutating_and_audit_routes_require_admin_session():
    review = client.patch(
        "/case-reviews/1",
        json={"review_status": "reviewed", "reviewer_comments": "Reviewed"},
    )
    history = client.get("/admin/audit-log")

    assert review.status_code == 401
    assert history.status_code == 401


def test_invoice_update_requires_admin_session():
    response = client.patch("/invoices/42", json={"taxable_amount": 150.00})

    assert response.status_code == 401


def test_invoice_update_records_old_and_new_values(monkeypatch):
    previous = {
        "invoice_id": 42,
        "invoice_number": "INV-42",
        "seller_taxpayer_id": 1,
        "buyer_taxpayer_id": 2,
        "invoice_date": date(2026, 6, 15),
        "taxable_amount": Decimal("100.00"),
        "output_vat": Decimal("16.00"),
        "item_description": "Original item",
    }
    updated = {**previous, "taxable_amount": Decimal("150.00")}
    cursor = MagicMock()
    cursor.fetchone.side_effect = [previous, updated]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch("/invoices/42", json={"taxable_amount": 150.00})
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 200
    assert Decimal(response.json()["taxable_amount"]) == Decimal("150.00")
    audit_insert = cursor.execute.call_args_list[-1]
    assert "invoice.updated" in audit_insert.args[0]
    assert audit_insert.args[1][0] == 7
    assert audit_insert.args[1][1] == "42"
    old_values = json.loads(audit_insert.args[1][2])
    new_values = json.loads(audit_insert.args[1][3])
    assert Decimal(old_values["taxable_amount"]) == Decimal("100.00")
    assert Decimal(new_values["taxable_amount"]) == Decimal("150.00")


def test_invoice_update_rejects_uneditable_fields():
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch("/invoices/42", json={"source_hash": "tampered"})
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 400


def test_session_creation_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)

    with pytest.raises(main.HTTPException) as error:
        main.encode_session("reviewer-one")

    assert error.value.status_code == 503


def test_first_admin_setup_rejects_invalid_token_before_database_access(monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", "setup-token-value-with-at-least-32-characters")
    monkeypatch.setattr(main, "get_connection", lambda: pytest.fail("Database must not be accessed"))

    response = client.post(
        "/admin/setup",
        json={
            "setup_token": "wrong-token",
            "username": "reviewer-one",
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "username,password",
    [
        ("", "correct horse battery staple"),
        ("x" * 81, "correct horse battery staple"),
        ("reviewer-one", "short"),
        ("reviewer-one", "x" * 1025),
    ],
)
def test_first_admin_setup_rejects_invalid_credentials_before_database_access(
    monkeypatch, username, password
):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", "setup-token-value-with-at-least-32-characters")
    monkeypatch.setattr(main, "get_connection", lambda: pytest.fail("Database must not be accessed"))

    response = client.post(
        "/admin/setup",
        json={
            "setup_token": "setup-token-value-with-at-least-32-characters",
            "username": username,
            "password": password,
        },
    )

    assert response.status_code == 400


def test_first_admin_setup_writes_bootstrap_audit_record(monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", "setup-token-value-with-at-least-32-characters")
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"has_admin": False}, {"administrator_id": 23}]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)

    response = client.post(
        "/admin/setup",
        json={
            "setup_token": "setup-token-value-with-at-least-32-characters",
            "username": "reviewer-one",
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 201
    assert response.json()["username"] == "reviewer-one"
    assert "LOCK TABLE core.administrator IN EXCLUSIVE MODE" in cursor.execute.call_args_list[0].args[0]
    audit_insert = cursor.execute.call_args_list[-1]
    assert "administrator.bootstrap" in audit_insert.args[0]
    assert json.loads(audit_insert.args[1][2]) == {"username": "reviewer-one"}


@pytest.mark.parametrize(
    "payload",
    [
        {"invoice_number": "   "},
        {"seller_taxpayer_id": 0},
        {"invoice_date": "2026-02-30"},
        {"taxable_amount": -0.01},
        {"taxable_amount": 0.001},
        {"taxable_amount": "NaN"},
        {"output_vat": "10000000000000000.00"},
    ],
)
def test_invoice_update_rejects_invalid_values_before_database_access(monkeypatch, payload):
    monkeypatch.setattr(main, "get_connection", lambda: pytest.fail("Database must not be accessed"))
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch("/invoices/42", json=payload)
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 400


def test_case_review_update_records_before_and_after_values(monkeypatch):
    previous = {"review_status": "pending", "reviewer_comments": None}
    updated = {"case_id": 8, "taxpayer_id": 12, "review_status": "reviewed", "reviewer_comments": "Verified"}
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"taxpayer_id": 12}, previous, updated]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch(
            "/case-reviews/12",
            json={"review_status": "reviewed", "reviewer_comments": "Verified"},
        )
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 200
    assert response.json()["reviewer_comments"] == "Verified"
    audit_insert = cursor.execute.call_args_list[-1]
    assert "case_review.updated" in audit_insert.args[0]
    assert audit_insert.args[1][0] == 7
    assert json.loads(audit_insert.args[1][2]) == previous
    assert json.loads(audit_insert.args[1][3]) == {
        "review_status": "reviewed",
        "reviewer_comments": "Verified",
    }


def test_case_review_rejects_invalid_status_before_database_access(monkeypatch):
    monkeypatch.setattr(main, "get_connection", lambda: pytest.fail("Database must not be accessed"))
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch("/case-reviews/12", json={"review_status": "approved"})
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 400


def test_logout_expires_session_cookie(monkeypatch):
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", "false")

    response = client.post("/admin/logout")

    assert response.status_code == 200
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_rejects_wrong_password_without_issuing_cookie(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"password_hash": main.hash_password("correct horse battery staple")}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)

    response = client.post("/admin/login", json={"username": "reviewer-one", "password": "wrong password"})

    assert response.status_code == 401
    assert main.SESSION_COOKIE not in response.cookies


def test_first_admin_setup_cannot_be_repeated(monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", "setup-token-value-with-at-least-32-characters")
    cursor = MagicMock()
    cursor.fetchone.return_value = {"has_admin": True}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)

    response = client.post(
        "/admin/setup",
        json={
            "setup_token": "setup-token-value-with-at-least-32-characters",
            "username": "second-admin",
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 409
    assert not any("INSERT INTO core.administrator" in call.args[0] for call in cursor.execute.call_args_list)


def test_case_review_returns_not_found_without_inserting_a_review(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.patch("/case-reviews/999999", json={"review_status": "reviewed"})
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 404
    assert len(cursor.execute.call_args_list) == 1


@pytest.mark.parametrize("requested_limit,expected_limit", [(0, 1), (1, 1), (100, 100), (9999, 500)])
def test_audit_log_limit_is_bounded(monkeypatch, requested_limit, expected_limit):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(main, "get_connection", lambda: connection)
    main.app.dependency_overrides[main.current_admin] = lambda: {
        "administrator_id": 7,
        "username": "reviewer-one",
    }

    try:
        response = client.get("/admin/audit-log", params={"limit": requested_limit})
    finally:
        main.app.dependency_overrides.pop(main.current_admin, None)

    assert response.status_code == 200
    assert cursor.execute.call_args.args[1] == (expected_limit,)