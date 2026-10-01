from datetime import date
from decimal import Decimal
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

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
    token = main.encode_session("reviewer-one")

    assert main.decode_session(token) == "reviewer-one"
    assert main.decode_session(token + "x") is None


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