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