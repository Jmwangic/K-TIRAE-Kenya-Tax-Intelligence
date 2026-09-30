import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

import psycopg
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/kra_anomaly",
)

app = FastAPI(title="KRA Tax Anomaly API", version="0.1.0")
SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 8 * 60 * 60
PASSWORD_ITERATIONS = 310_000


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def hash_password(password: str) -> str:
  salt = secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
  return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
  try:
    iterations_text, salt_hex, expected_hex = stored_hash.split("$", 2)
    iterations = int(iterations_text)
    if iterations < 100_000 or iterations > 2_000_000:
      return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), iterations)
    return hmac.compare_digest(actual.hex(), expected_hex)
  except (ValueError, TypeError):
    return False


def encode_session(username: str) -> str:
  secret = os.environ.get("ADMIN_SESSION_SECRET", "").encode()
  if len(secret) < 32:
    raise HTTPException(status_code=503, detail="Administrator sessions are not configured")
  payload = json.dumps({"username": username, "exp": int(time.time()) + SESSION_MAX_AGE}).encode()
  encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
  signature = hmac.new(secret, encoded, hashlib.sha256).digest()
  return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def decode_session(token: str) -> str | None:
  secret = os.environ.get("ADMIN_SESSION_SECRET", "").encode()
  if len(secret) < 32:
    return None
  try:
    payload_part, signature_part = token.split(".", 1)
    signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
    expected = hmac.new(secret, payload_part.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
      return None
    payload = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
    session = json.loads(payload)
    if session["exp"] <= time.time() or not isinstance(session["username"], str):
      return None
    return session["username"]
  except (ValueError, KeyError, TypeError, json.JSONDecodeError):
    return None


def set_session_cookie(response: Response, username: str) -> None:
  response.set_cookie(
    SESSION_COOKIE,
    encode_session(username),
    max_age=SESSION_MAX_AGE,
    httponly=True,
    secure=os.environ.get("ADMIN_COOKIE_SECURE", "false").lower() == "true",
    samesite="strict",
    path="/",
  )


def current_admin(request: Request) -> dict[str, Any]:
  token = request.cookies.get(SESSION_COOKIE, "")
  username = decode_session(token)
  if username is None:
    raise HTTPException(status_code=401, detail="Administrator sign-in required")
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        "SELECT administrator_id, username FROM core.administrator WHERE username = %s AND enabled",
        (username,),
      )
      admin = cur.fetchone()
  if admin is None:
    raise HTTPException(status_code=401, detail="Administrator account is disabled or unavailable")
  return admin


def validate_admin_credentials(username: str, password: str) -> None:
  if not username or len(username) > 80:
    raise HTTPException(status_code=400, detail="Username must be between 1 and 80 characters")
  if len(password) < 12 or len(password) > 1024:
    raise HTTPException(status_code=400, detail="Password must be between 12 and 1024 characters")


@app.get("/admin/session")
def admin_session(request: Request) -> dict[str, Any]:
  token = request.cookies.get(SESSION_COOKIE, "")
  username = decode_session(token) if token else None
  if username:
    with get_connection() as conn:
      with conn.cursor() as cur:
        cur.execute(
          "SELECT administrator_id, username FROM core.administrator WHERE username = %s AND enabled",
          (username,),
        )
        admin = cur.fetchone()
    if admin:
      return {"administrator": admin, "setup_required": False}
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute("SELECT EXISTS (SELECT 1 FROM core.administrator WHERE enabled) AS has_admin")
      has_admin = cur.fetchone()["has_admin"]
  return {"administrator": None, "setup_required": not has_admin}


@app.post("/admin/setup", status_code=201)
def setup_first_admin(payload: dict[str, str] = Body(...)) -> dict[str, str]:
  configured_token = os.environ.get("ADMIN_SETUP_TOKEN", "")
  if len(configured_token) < 32:
    raise HTTPException(status_code=503, detail="First-administrator setup is not configured")
  if not hmac.compare_digest(payload.get("setup_token", ""), configured_token):
    raise HTTPException(status_code=401, detail="Invalid setup token")
  username = payload.get("username", "").strip()
  password = payload.get("password", "")
  validate_admin_credentials(username, password)
  password_hash = hash_password(password)
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute("LOCK TABLE core.administrator IN EXCLUSIVE MODE")
      cur.execute("SELECT EXISTS (SELECT 1 FROM core.administrator) AS has_admin")
      if cur.fetchone()["has_admin"]:
        raise HTTPException(status_code=409, detail="Administrator setup has already been completed")
      cur.execute(
        "INSERT INTO core.administrator (username, password_hash) VALUES (%s, %s) RETURNING administrator_id",
        (username, password_hash),
      )
      administrator_id = cur.fetchone()["administrator_id"]
      cur.execute(
        """INSERT INTO audit.admin_change_log
           (administrator_id, action, entity_type, entity_id, new_values)
           VALUES (%s, 'administrator.bootstrap', 'administrator', %s, %s::jsonb)""",
        (administrator_id, username, json.dumps({"username": username})),
      )
  return {"username": username, "message": "Administrator created; sign in to continue"}


@app.post("/admin/login")
def admin_login(payload: dict[str, str] = Body(...), response: Response = None) -> dict[str, str]:
  username = payload.get("username", "").strip()
  password = payload.get("password", "")
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        "SELECT password_hash FROM core.administrator WHERE username = %s AND enabled",
        (username,),
      )
      row = cur.fetchone()
  if row is None or not verify_password(password, row["password_hash"]):
    raise HTTPException(status_code=401, detail="Invalid username or password")
  if response is None:
    raise HTTPException(status_code=500, detail="Could not create administrator session")
  set_session_cookie(response, username)
  return {"username": username}


@app.post("/admin/logout")
def admin_logout(response: Response) -> dict[str, str]:
  response.delete_cookie(
    SESSION_COOKIE,
    path="/",
    secure=os.environ.get("ADMIN_COOKIE_SECURE", "false").lower() == "true",
    httponly=True,
    samesite="strict",
  )
  return {"message": "Signed out"}


@app.post("/admin/administrators", status_code=201)
def create_admin(
  payload: dict[str, str] = Body(...),
  admin: dict[str, Any] = Depends(current_admin),
) -> dict[str, str]:
  username = payload.get("username", "").strip()
  password = payload.get("password", "")
  validate_admin_credentials(username, password)
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        "INSERT INTO core.administrator (username, password_hash) VALUES (%s, %s) RETURNING administrator_id",
        (username, hash_password(password)),
      )
      created = cur.fetchone()
      cur.execute(
        """INSERT INTO audit.admin_change_log
           (administrator_id, action, entity_type, entity_id, new_values)
           VALUES (%s, 'administrator.created', 'administrator', %s, %s::jsonb)""",
        (admin["administrator_id"], username, json.dumps({"username": username})),
      )
  return {"username": username, "administrator_id": str(created["administrator_id"])}


@app.get("/admin/audit-log")
def get_admin_audit_log(
  admin: dict[str, Any] = Depends(current_admin), limit: int = 100
) -> list[dict[str, Any]]:
  bounded_limit = max(1, min(limit, 500))
  with get_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
        """SELECT l.log_id, a.username, l.action, l.entity_type, l.entity_id,
              l.old_values, l.new_values, l.changed_at
           FROM audit.admin_change_log l
           JOIN core.administrator a ON a.administrator_id = l.administrator_id
           ORDER BY l.changed_at DESC, l.log_id DESC LIMIT %s""",
        (bounded_limit,),
      )
      return cur.fetchall()


@app.get("/", response_class=HTMLResponse)
def dashboard_page() -> str:
    return """
    <html>
      <head>
        <title>KRA Tax Anomaly Dashboard</title>
        <style>
          :root {
            --kra-blue: #0f4c81;
            --kra-blue-dark: #0a3557;
            --kra-gold: #f5b700;
            --kra-gold-soft: #fff1b8;
            --kra-green: #1e7a5d;
            --kra-green-soft: #dff7ef;
            --kra-red: #c13d3d;
            --kra-red-soft: #fde6e6;
            --kra-slate: #17324a;
            --kra-bg: #edf3f9;
            --kra-card: #ffffff;
            --kra-text: #18314f;
            --kra-muted: #58728a;
          }
          body { font-family: Arial, sans-serif; margin: 0; background: linear-gradient(180deg, var(--kra-bg) 0%, #f7fafc 100%); color: var(--kra-text); }
          .page-shell { max-width: 1500px; margin: 0 auto; padding: 28px 22px 40px; }
          .header-panel { background: linear-gradient(135deg, var(--kra-blue-dark) 0%, var(--kra-blue) 55%, var(--kra-gold) 160%); color: white; border-radius: 18px; padding: 28px 30px; margin-bottom: 22px; box-shadow: 0 16px 28px rgba(15, 76, 129, 0.22); }
          .admin-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 12px 0; margin: -12px 0 16px; border-bottom: 1px solid #d7e3ed; }
          .admin-state { color: var(--kra-muted); font-size: 13px; }
          .admin-actions { display: flex; gap: 8px; flex-wrap: wrap; }
          .admin-login { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
          .admin-input { border: 1px solid #bfd4ea; border-radius: 6px; padding: 8px 10px; font-size: 13px; }
          .audit-panel { margin: 0 0 20px; background: white; border: 1px solid #dfeaf5; border-radius: 8px; padding: 16px; }
          .audit-panel[hidden] { display: none; }
          h1 { margin: 0; font-size: 40px; letter-spacing: -0.04em; }
          .subtitle { margin-top: 10px; color: #e9f4ff; font-size: 15px; }
          .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin: 18px 0 24px; }
          .metric { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); border-radius: 16px; padding: 18px 18px 16px; box-shadow: 0 6px 18px rgba(15, 76, 129, 0.08); border-left: 6px solid #d9e5ef; }
          .metric:nth-child(1) { border-left-color: var(--kra-blue); }
          .metric:nth-child(2) { border-left-color: var(--kra-green); }
          .metric:nth-child(3) { border-left-color: var(--kra-gold); }
          .metric:nth-child(4) { border-left-color: var(--kra-red); }
          .metric-label { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--kra-muted); }
          .metric-value { display: block; font-size: 30px; font-weight: 800; margin-top: 10px; line-height: 1.1; }
          .metric-note { display: block; color: var(--kra-muted); font-size: 12px; margin-top: 4px; }
          .priority-panel { margin: 0 0 22px; background: white; border-radius: 18px; box-shadow: 0 8px 20px rgba(15, 76, 129, 0.08); border: 1px solid #dfeaf5; padding: 18px 20px; }
          .priority-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
          .priority-title { font-size: 18px; font-weight: 800; color: var(--kra-blue-dark); }
          .priority-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .priority-item { border: 1px solid #dfeaf5; border-radius: 12px; background: linear-gradient(180deg, #ffffff 0%, #f8fbfe 100%); padding: 14px 14px 12px; }
          .priority-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
          .priority-taxpayer { font-weight: 800; color: var(--kra-blue-dark); }
          .priority-risk { font-size: 12px; font-weight: 800; color: #0f172a; }
          .priority-type { margin-top: 8px; font-size: 13px; color: var(--kra-muted); }
          .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 8px 0 18px; flex-wrap: wrap; }
          .legend { display: flex; gap: 10px; flex-wrap: wrap; }
          .legend-item { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #475569; }
          .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
          .filter-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
          .filter-btn { border: 1px solid #bfd4ea; background: white; border-radius: 999px; padding: 7px 14px; font-size: 12px; font-weight: 700; color: var(--kra-slate); cursor: pointer; box-shadow: 0 1px 2px rgba(15, 76, 129, 0.08); }
          .filter-btn.active { background: var(--kra-blue); color: white; border-color: var(--kra-blue); }
          .action-btn { border: 1px solid var(--kra-gold); background: linear-gradient(180deg, #fff8dd 0%, #fff0b3 100%); border-radius: 999px; padding: 8px 14px; font-size: 12px; font-weight: 800; color: var(--kra-blue-dark); cursor: pointer; box-shadow: 0 2px 8px rgba(245, 183, 0, 0.2); }
          .risk-pill { display: inline-flex; min-width: 86px; align-items: center; justify-content: center; border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 800; }
          .detail-panel { margin: 0 0 18px; background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%); border: 1px solid #dfe7f1; border-radius: 16px; padding: 18px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }
          .detail-panel.hidden { display: none; }
          .detail-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
          .detail-title { font-size: 18px; font-weight: 800; }
          .detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 12px; }
          .detail-item { background: white; border: 1px solid #edf2f7; border-radius: 12px; padding: 10px 12px; }
          .detail-label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: #64748b; }
          .detail-value { display: block; margin-top: 6px; font-size: 18px; font-weight: 700; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
          .card { background: white; border-radius: 18px; padding: 18px 18px 12px; box-shadow: 0 10px 24px rgba(15, 76, 129, 0.08); overflow: visible; }
          .card.full-width { grid-column: 1 / -1; }
          .card h2 { margin: 0 0 8px; font-size: 20px; color: var(--kra-blue-dark); }
          .executive-panel { display: none; background: linear-gradient(180deg, #fefdf7 0%, #fffaf0 100%); border: 1px solid #f2d57d; border-radius: 18px; padding: 20px; margin: 0 0 20px; box-shadow: 0 8px 20px rgba(245, 183, 0, 0.08); }
          .executive-mode .executive-panel { display: block; }
          .executive-mode .grid { display: none; }
          .exec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .exec-item { background: #fff; border: 1px solid #f2d57d; border-radius: 12px; padding: 12px 14px; }
          .exec-item strong { display: block; color: var(--kra-blue-dark); margin-bottom: 6px; }
          table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 8px; table-layout: auto; }
          th, td { border-bottom: 1px solid #e2e8f0; text-align: left; padding: 14px 10px; vertical-align: middle; white-space: normal; word-break: break-word; overflow-wrap: anywhere; font-size: 15px; line-height: 1.45; }
          th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: #64748b; background: #f8fafc; }
          tbody tr { min-height: 60px; }
          tbody tr:nth-child(even) { background: #f8fafc; }
          tbody tr:hover { background: #eff6ff; }
          .status { font-weight: 700; display: inline-flex; align-items: center; justify-content: center; padding: 6px 10px; border-radius: 999px; white-space: nowrap; min-width: 100px; }
          .matched { background: rgba(22, 163, 74, 0.12); color: #166534; }
          .warning { background: rgba(245, 158, 11, 0.12); color: #b45309; }
          .alert { background: rgba(220, 38, 38, 0.12); color: #b91c1c; }
          .finding-label { display: inline-block; line-height: 1.4; }
          .muted { color: #64748b; }
          .review-btn { border: 1px solid #bfd4ea; background: white; border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 700; color: var(--kra-blue-dark); cursor: pointer; }
          .review-btn:hover { background: #eff6ff; }
          .search-panel { margin: 0 0 22px; background: white; border-radius: 18px; padding: 18px 20px; box-shadow: 0 8px 20px rgba(15, 76, 129, 0.08); border: 1px solid #dfeaf5; }
          .search-form { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
          .search-input { flex: 1 1 320px; min-width: 220px; border: 1px solid #bfd4ea; border-radius: 8px; padding: 10px 12px; color: var(--kra-text); font-size: 14px; }
          .search-input:focus { outline: 3px solid rgba(15, 76, 129, 0.14); border-color: var(--kra-blue); }
          .search-results { overflow-x: auto; margin-top: 14px; }
          .search-results table { min-width: 820px; }
          .risk-table { min-width: 820px; table-layout: fixed; }
          .risk-table th { white-space: nowrap; }
          .risk-table th:nth-child(1) { width: 9%; }
          .risk-table th:nth-child(2) { width: 12%; }
          .risk-table th:nth-child(3) { width: 14%; }
          .risk-table th:nth-child(4) { width: 38%; }
          .risk-table th:nth-child(5) { width: 12%; }
          .risk-table th:nth-child(6) { width: 15%; }
          .risk-table td:nth-child(4) { min-width: 280px; }
          .risk-table .status, .risk-table .risk-pill, .risk-table .review-btn { white-space: nowrap; }
          @media (max-width: 1100px) {
            .grid { grid-template-columns: 1fr; }
            .card { overflow-x: auto; }
          }
        </style>
      </head>
      <body>
        <div class="page-shell">
          <div class="header-panel">
            <h1>KRA Tax Anomaly Dashboard</h1>
            <div class="subtitle">Operational review of reconciliation, risk results, duplicate invoices, and case decisions.</div>
          </div>

          <div class="admin-bar">
            <div id="admin-state" class="admin-state">Checking administrator session...</div>
            <div id="admin-actions" class="admin-actions"></div>
          </div>

          <section id="audit-panel" class="audit-panel" hidden>
            <div class="priority-header">
              <div class="priority-title">Administrator change history</div>
              <button class="review-btn" id="close-audit-log" type="button" aria-label="Close administrator history">Close</button>
            </div>
            <div class="search-results" id="audit-log-results"></div>
          </section>

          <div id="summary" class="summary"></div>

          <div class="search-panel">
            <div class="priority-header">
              <div class="priority-title">Taxpayer search</div>
              <div class="muted">Review sales, risk, and case status together</div>
            </div>
            <form id="taxpayer-search-form" class="search-form">
              <input id="taxpayer-search-input" class="search-input" type="search" placeholder="Search by PIN or business name" aria-label="Search by PIN or business name">
              <button class="action-btn" type="submit">Search</button>
            </form>
            <div id="taxpayer-search-results" class="search-results" hidden></div>
          </div>

          <div id="priority-panel" class="priority-panel">
            <div class="priority-header">
              <div class="priority-title">Top risk items</div>
              <div class="muted">Highest priority review list</div>
            </div>
            <div id="priority-list" class="priority-list"></div>
          </div>

          <div id="detail-panel" class="detail-panel hidden">
            <div class="detail-header">
              <div class="detail-title" id="detail-title">Selected issue</div>
              <div id="detail-severity" class="status matched">Low</div>
            </div>
            <div class="detail-grid" id="detail-grid"></div>
          </div>

          <div class="toolbar">
            <div class="legend">
              <span class="legend-item"><span class="dot" style="background:#1e7a5d"></span> Matched</span>
              <span class="legend-item"><span class="dot" style="background:#f5b700"></span> Warning</span>
              <span class="legend-item"><span class="dot" style="background:#c13d3d"></span> Critical</span>
            </div>
            <div class="filter-buttons">
              <button class="filter-btn" data-filter="all">All</button>
              <button class="filter-btn active" data-filter="anomaly">Anomalies only</button>
              <button class="filter-btn" data-filter="matched">Matched only</button>
              <button class="action-btn" id="executive-toggle">Executive view</button>
              <button class="action-btn" id="print-report">Print report</button>
            </div>
          </div>

          <div id="executive-panel" class="executive-panel">
            <div class="priority-header">
              <div class="priority-title">Executive summary</div>
              <div class="muted">Board-ready risk overview</div>
            </div>
            <div id="executive-summary-grid" class="exec-grid"></div>
          </div>

          <div class="grid">
            <div class="card full-width">
              <h2>Reconciliation findings</h2>
              <table data-table-key="findings">
                <thead>
                  <tr>
                    <th data-sort-key="taxpayer_id">Taxpayer</th>
                    <th data-sort-key="event_date">Date</th>
                    <th data-sort-key="finding_type">Finding</th>
                    <th data-sort-key="risk_score">Risk</th>
                    <th data-sort-key="etims_taxable_amount">ETIMS</th>
                    <th data-sort-key="customs_value">Customs</th>
                    <th data-sort-key="variance">Variance</th>
                  </tr>
                </thead>
                <tbody id="findings-body"></tbody>
              </table>
            </div>
            <div class="card full-width">
              <h2>Risk results and case review</h2>
              <table class="risk-table" data-table-key="risk">
                <thead>
                  <tr>
                    <th data-sort-key="taxpayer_id">Taxpayer</th>
                    <th data-sort-key="risk_score">Score</th>
                    <th data-sort-key="risk_level">Level</th>
                    <th>Reason</th>
                    <th data-sort-key="review_status">Review</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody id="risk-body"></tbody>
              </table>
            </div>
            <div class="card">
              <h2>Duplicate invoice numbers</h2>
              <table data-table-key="duplicates">
                <thead>
                  <tr>
                    <th data-sort-key="invoice_number">Invoice</th>
                    <th data-sort-key="occurrence_count">Occurrences</th>
                    <th data-sort-key="buyer_taxpayer_ids">Buyers</th>
                  </tr>
                </thead>
                <tbody id="duplicates-body"></tbody>
              </table>
            </div>
            <div class="card">
              <h2>Invoice timing gaps</h2>
              <table data-table-key="gaps">
                <thead>
                  <tr>
                    <th data-sort-key="buyer_taxpayer_id">Buyer</th>
                    <th data-sort-key="invoice_number">Invoice</th>
                    <th data-sort-key="invoice_date">Invoice date</th>
                    <th data-sort-key="previous_invoice_date">Prev date</th>
                    <th data-sort-key="days_since_previous_invoice">Days gap</th>
                  </tr>
                </thead>
                <tbody id="gaps-body"></tbody>
              </table>
            </div>
          </div>
        </div>

        <script>
          let signedInAdmin = null;

          function escapeHTML(value) {
            return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
          }

          async function refreshAdminSession() {
            const response = await fetch('/admin/session');
            const session = await response.json();
            signedInAdmin = session.administrator;
            const state = document.getElementById('admin-state');
            const actions = document.getElementById('admin-actions');
            if (signedInAdmin) {
              state.textContent = `Signed in as ${signedInAdmin.username}`;
              actions.innerHTML = '<button class="review-btn" id="show-audit-log" type="button">Change history</button><button class="review-btn" id="add-admin" type="button">Add administrator</button><button class="review-btn" id="admin-logout" type="button">Sign out</button>';
              document.getElementById('show-audit-log').addEventListener('click', loadAuditLog);
              document.getElementById('add-admin').addEventListener('click', addAdministrator);
              document.getElementById('admin-logout').addEventListener('click', signOutAdmin);
            } else {
              state.textContent = session.setup_required ? 'No administrator exists yet. Complete first-admin setup.' : 'Administrator sign-in required to change case reviews.';
              actions.innerHTML = session.setup_required
                ? '<button class="action-btn" id="setup-admin" type="button">Set up first administrator</button>'
                : '<form class="admin-login" id="admin-login"><input class="admin-input" name="username" autocomplete="username" placeholder="Username" required><input class="admin-input" name="password" type="password" autocomplete="current-password" placeholder="Password" required><button class="action-btn" type="submit">Sign in</button></form>';
              if (session.setup_required) document.getElementById('setup-admin').addEventListener('click', setupFirstAdmin);
              else document.getElementById('admin-login').addEventListener('submit', loginAdmin);
            }
          }

          async function loginAdmin(event) {
            event.preventDefault();
            const values = Object.fromEntries(new FormData(event.currentTarget));
            const response = await fetch('/admin/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
            if (!response.ok) { window.alert('Sign-in failed. Check your username and password.'); return; }
            await refreshAdminSession();
            loadRiskResults();
          }

          async function setupFirstAdmin() {
            const setupToken = window.prompt('Enter the one-time administrator setup token');
            if (setupToken === null) return;
            const username = window.prompt('Choose an administrator username');
            if (username === null) return;
            const password = window.prompt('Choose a password with at least 12 characters');
            if (password === null) return;
            const response = await fetch('/admin/setup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ setup_token: setupToken, username, password }) });
            if (!response.ok) { window.alert('Administrator setup failed. Check the setup token and password requirements.'); return; }
            window.alert('Administrator created. Sign in with the new account.');
            await refreshAdminSession();
          }

          async function addAdministrator() {
            const username = window.prompt('New administrator username');
            if (username === null) return;
            const password = window.prompt('Temporary password (at least 12 characters)');
            if (password === null) return;
            const response = await fetch('/admin/administrators', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
            if (!response.ok) { window.alert('Administrator could not be added.'); return; }
            window.alert('Administrator account created. Share the temporary password securely.');
          }

          async function signOutAdmin() {
            await fetch('/admin/logout', { method: 'POST' });
            document.getElementById('audit-panel').hidden = true;
            await refreshAdminSession();
            loadRiskResults();
          }

          async function loadAuditLog() {
            const response = await fetch('/admin/audit-log');
            if (!response.ok) { window.alert('Administrator history could not be loaded.'); return; }
            const entries = await response.json();
            const container = document.getElementById('audit-log-results');
            container.innerHTML = entries.length ? `<table><thead><tr><th>When</th><th>Administrator</th><th>Action</th><th>Record</th><th>Before</th><th>After</th></tr></thead><tbody>${entries.map((entry) => `<tr><td>${escapeHTML(new Date(entry.changed_at).toLocaleString())}</td><td>${escapeHTML(entry.username)}</td><td>${escapeHTML(entry.action)}</td><td>${escapeHTML(`${entry.entity_type} ${entry.entity_id}`)}</td><td>${escapeHTML(JSON.stringify(entry.old_values ?? {}))}</td><td>${escapeHTML(JSON.stringify(entry.new_values ?? {}))}</td></tr>`).join('')}</tbody></table>` : '<div class="muted">No administrator changes have been recorded.</div>';
            document.getElementById('audit-panel').hidden = false;
          }

          document.addEventListener('click', (event) => {
            if (event.target.id === 'close-audit-log') document.getElementById('audit-panel').hidden = true;
          });

          const sortState = {
            findings: { key: 'risk_score', direction: 'desc' },
            risk: { key: 'risk_score', direction: 'desc' },
            duplicates: { key: 'occurrence_count', direction: 'desc' },
            gaps: { key: 'days_since_previous_invoice', direction: 'desc' }
          };

          function computeRiskScore(row) {
            const base = row.finding_type === 'matched' ? 0 : row.finding_type === 'amount_mismatch' ? 68 : 86;
            const amountSpread = Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0));
            const varianceBoost = Math.min(18, amountSpread / 1000000);
            return Math.round(base + varianceBoost);
          }

          function getSeverity(type) {
            if (type === 'matched') return { label: 'Low', cls: 'matched' };
            if (type === 'amount_mismatch') return { label: 'Medium', cls: 'warning' };
            return { label: 'High', cls: 'alert' };
          }

          function formatMoney(value) {
            const num = Number(value || 0);
            return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
          }

          function renderTaxpayerSearch(rows) {
            const container = document.getElementById('taxpayer-search-results');
            container.hidden = false;
            if (!rows.length) {
              container.innerHTML = '<div class="muted">No taxpayers matched that search.</div>';
              return;
            }

            container.innerHTML = `
              <table>
                <thead><tr><th>PIN</th><th>Business</th><th>Recorded sales</th><th>Declared sales</th><th>Variance</th><th>Risk</th><th>Review</th></tr></thead>
                <tbody>${rows.map((row) => `
                  <tr>
                    <td>${row.kra_pin}</td>
                    <td>${row.legal_name}</td>
                    <td>${formatMoney(row.recorded_sales)}</td>
                    <td>${formatMoney(row.declared_sales)}</td>
                    <td>${formatMoney(row.sales_variance)}</td>
                    <td><span class="risk-pill ${riskClass(row.risk_level)}">${row.risk_score}/100</span></td>
                    <td>${row.review_status}</td>
                  </tr>
                `).join('')}</tbody>
              </table>
            `;
          }

          function bindTaxpayerSearch() {
            document.getElementById('taxpayer-search-form').addEventListener('submit', async (event) => {
              event.preventDefault();
              const query = document.getElementById('taxpayer-search-input').value.trim();
              const response = await fetch(`/taxpayers/search?q=${encodeURIComponent(query)}`);
              if (!response.ok) {
                renderTaxpayerSearch([]);
                return;
              }
              renderTaxpayerSearch(await response.json());
            });
          }

          function renderPriorityList(rows) {
            const panel = document.getElementById('priority-list');
            const anomalies = rows.filter((row) => row.finding_type !== 'matched').slice().sort((a, b) => computeRiskScore(b) - computeRiskScore(a)).slice(0, 5);

            if (!anomalies.length) {
              panel.innerHTML = '<div class="priority-item"><div class="priority-type">No anomalies in the current filter.</div></div>';
              return;
            }

            panel.innerHTML = anomalies.map((row) => {
              const info = getSeverity(row.finding_type || 'matched');
              return `
                <div class="priority-item">
                  <div class="priority-row">
                    <div class="priority-taxpayer">${row.taxpayer_id}</div>
                    <span class="status ${info.cls} priority-risk">${computeRiskScore(row)}/100</span>
                  </div>
                  <div class="priority-type">${row.finding_type}</div>
                  <div class="muted" style="margin-top: 8px;">${row.event_date} · ${formatMoney(Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0)))}</div>
                </div>
              `;
            }).join('');
          }

          function renderExecutiveSummary(rows) {
            const container = document.getElementById('executive-summary-grid');
            const anomalies = rows.filter((row) => row.finding_type !== 'matched').slice().sort((a, b) => computeRiskScore(b) - computeRiskScore(a)).slice(0, 4);

            const summary = [
              ['Highest-risk taxpayer', anomalies[0]?.taxpayer_id || 'N/A'],
              ['Most urgent issue', anomalies[0]?.finding_type || 'No anomalies'],
              ['Anomaly count', rows.filter((row) => row.finding_type !== 'matched').length],
              ['Watchlist size', anomalies.length]
            ];

            container.innerHTML = summary.map(([label, value]) => `
              <div class="exec-item">
                <strong>${label}</strong>
                <div>${value}</div>
              </div>
            `).join('');
          }

          function showDetail(row) {
            const panel = document.getElementById('detail-panel');
            const grid = document.getElementById('detail-grid');
            const title = document.getElementById('detail-title');
            const severity = document.getElementById('detail-severity');
            const info = getSeverity(row.finding_type || 'matched');

            title.textContent = `${row.taxpayer_id || row.buyer_taxpayer_id || 'Record'} — ${row.finding_type || 'Record detail'}`;
            severity.textContent = info.label;
            severity.className = `status ${info.cls}`;

            const fields = [
              ['Taxpayer', row.taxpayer_id ?? row.buyer_taxpayer_id ?? '-'],
              ['Date', row.event_date ?? row.invoice_date ?? row.previous_invoice_date ?? '-'],
              ['Finding', row.finding_type ?? 'Record detail'],
              ['Risk score', `${computeRiskScore(row)}/100`],
              ['ETIMS', formatMoney(row.etims_taxable_amount ?? 0)],
              ['Customs', formatMoney(row.customs_value ?? 0)],
              ['Variance', formatMoney(Math.abs(Number(row.etims_taxable_amount || 0) - Number(row.customs_value || 0)))],
              ['Invoice', row.invoice_number ?? '-'],
              ['Occurrences', row.occurrence_count ?? '-'],
              ['Buyers', Array.isArray(row.buyer_taxpayer_ids) ? row.buyer_taxpayer_ids.join(', ') : (row.buyer_taxpayer_ids ?? '-')],
              ['Days gap', row.days_since_previous_invoice ?? '-']
            ];

            grid.innerHTML = fields
              .filter(([, value]) => value !== '-'
                || (Array.isArray(value) && value.length > 0))
              .map(([label, value]) => `
                <div class="detail-item">
                  <span class="detail-label">${label}</span>
                  <span class="detail-value">${value}</span>
                </div>
              `)
              .join('');

            panel.classList.remove('hidden');
          }

          async function loadSummary() {
            const res = await fetch('/summary');
            const summary = await res.json();
            const el = document.getElementById('summary');
            el.innerHTML = `
              <div class="metric">
                <span class="metric-label">Taxpayers analysed</span>
                <span class="metric-value">${summary.total_taxpayers}</span>
                <span class="metric-note">Synthetic review population</span>
              </div>
              <div class="metric">
                <span class="metric-label">Flagged taxpayers</span>
                <span class="metric-value">${summary.flagged_taxpayers}</span>
                <span class="metric-note">Require prioritisation</span>
              </div>
              <div class="metric">
                <span class="metric-label">Sales variance</span>
                <span class="metric-value">${formatMoney(summary.total_sales_variance)}</span>
                <span class="metric-note">Recorded versus declared</span>
              </div>
              <div class="metric">
                <span class="metric-label">Total findings</span>
                <span class="metric-value">${summary.total_findings}</span>
                <span class="metric-note">${summary.anomaly_findings} operational issues</span>
              </div>
              <div class="metric">
                <span class="metric-label">Matched</span>
                <span class="metric-value">${summary.matched_findings}</span>
                <span class="metric-note">Fully reconciled records</span>
              </div>
              <div class="metric">
                <span class="metric-label">Duplicates</span>
                <span class="metric-value">${summary.total_duplicates}</span>
                <span class="metric-note">Repeat invoice numbers</span>
              </div>
              <div class="metric">
                <span class="metric-label">Timing gaps</span>
                <span class="metric-value">${summary.total_timing_gaps}</span>
                <span class="metric-note">More than 30 days apart</span>
              </div>
            `;
          }

          function riskClass(level) {
            if (level === 'high') return 'alert';
            if (level === 'medium') return 'warning';
            return 'matched';
          }

          function renderRiskResults(rows, key = sortState.risk.key, direction = sortState.risk.direction) {
            const tbody = document.getElementById('risk-body');
            if (!tbody) return;

            const sorted = sortRows(rows, key, direction);
            tbody.innerHTML = sorted.length ? sorted.map((row) => `
              <tr>
                <td>${row.taxpayer_id}</td>
                <td><span class="risk-pill ${riskClass(row.risk_level)}">${row.risk_score}/100</span></td>
                <td class="status ${riskClass(row.risk_level)}">${row.risk_level}</td>
                <td>${row.reason}</td>
                <td>${row.review_status}</td>
                    <td><button class="review-btn" data-taxpayer-id="${row.taxpayer_id}" data-status="${row.review_status}" ${signedInAdmin ? '' : 'disabled title="Sign in as an administrator to update reviews"'}>${row.review_status === 'reviewed' ? 'Reopen' : 'Mark reviewed'}</button></td>
              </tr>
            `).join('') : '<tr><td colspan="6">No risk results</td></tr>';

            tbody.querySelectorAll('.review-btn').forEach((button) => {
              button.addEventListener('click', async () => {
                const taxpayerId = button.dataset.taxpayerId;
                const reviewed = button.dataset.status !== 'reviewed';
                const comments = window.prompt('Reviewer comments', '')
                  ?? '';
                const response = await fetch(`/case-reviews/${taxpayerId}`, {
                  method: 'PATCH',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    review_status: reviewed ? 'reviewed' : 'pending',
                    reviewer_comments: comments
                  })
                });
                if (!response.ok) {
                  window.alert('The case review could not be saved.');
                  return;
                }
                loadRiskResults();
              });
            });
          }

          async function loadRiskResults() {
            const response = await fetch('/risk-results');
            const rows = await response.json();
            renderRiskResults(rows);
            attachSortHandlers('risk', rows, renderRiskResults);
          }

          function sortRows(rows, key, direction) {
            const dir = direction === 'asc' ? 1 : -1;

            return [...rows].sort((a, b) => {
              let left = a[key];
              let right = b[key];

              if (key === 'event_date' || key === 'invoice_date' || key === 'previous_invoice_date') {
                left = Date.parse(left || '1970-01-01');
                right = Date.parse(right || '1970-01-01');
              } else if (key === 'risk_score' || key === 'taxpayer_id' || key === 'buyer_taxpayer_id' || key === 'occurrence_count' || key === 'days_since_previous_invoice' || key === 'etims_taxable_amount' || key === 'customs_value' || key === 'variance') {
                left = Number(left || 0);
                right = Number(right || 0);
              } else if (Array.isArray(left)) {
                left = left.join(', ');
                right = Array.isArray(right) ? right.join(', ') : right;
              }

              if (left < right) return -1 * dir;
              if (left > right) return 1 * dir;
              return 0;
            });
          }

          function attachSortHandlers(tableKey, rows, renderFunc) {
            const table = document.querySelector(`table[data-table-key="${tableKey}"]`);
            if (!table) return;

            table.querySelectorAll('th[data-sort-key]').forEach((header) => {
              header.style.cursor = 'pointer';
              header.addEventListener('click', () => {
                const key = header.dataset.sortKey;
                const current = sortState[tableKey];

                if (current.key === key) {
                  current.direction = current.direction === 'asc' ? 'desc' : 'asc';
                } else {
                  current.key = key;
                  current.direction = 'asc';
                }

                renderFunc(rows, current.key, current.direction);
              });
            });
          }

          function renderFindingsTable(rows, key = 'taxpayer_id', direction = 'asc', filter = 'anomaly') {
            const tbody = document.getElementById('findings-body');
            if (!tbody) return;

            const filtered = rows.filter((row) => {
              if (filter === 'all') return true;
              if (filter === 'anomaly') return row.finding_type !== 'matched';
              if (filter === 'matched') return row.finding_type === 'matched';
              return true;
            });

            const sorted = sortRows(filtered, key, direction);
            tbody.innerHTML = '';

            if (!sorted.length) {
              tbody.innerHTML = '<tr><td colspan="6">No records match this filter</td></tr>';
              return;
            }

            sorted.forEach((row) => {
              const tr = document.createElement('tr');
              tr._rowData = row;
              tr.innerHTML = formatFinding(row);
              tr.addEventListener('click', () => showDetail(row));
              tbody.appendChild(tr);
            });
          }

          function renderGenericTable(tableKey, endpoint, formatter, columns, rowsOverride) {
            const tbody = document.getElementById(`${tableKey}-body`);
            if (!tbody) return;

            const render = (rows, key = sortState[tableKey].key, direction = sortState[tableKey].direction) => {
              const sorted = sortRows(rows, key, direction);
              tbody.innerHTML = '';
              if (!sorted.length) {
                tbody.innerHTML = `<tr><td colspan="${columns}">No records</td></tr>`;
                return;
              }
              sorted.forEach((row) => {
                const tr = document.createElement('tr');
                tr._rowData = row;
                tr.innerHTML = formatter(row);
                tr.addEventListener('click', () => showDetail(row));
                tbody.appendChild(tr);
              });
            };

            if (rowsOverride) {
              render(rowsOverride);
              attachSortHandlers(tableKey, rowsOverride, render);
              return;
            }

            fetch(endpoint)
              .then((response) => response.json())
              .then((rows) => {
                render(rows);
                attachSortHandlers(tableKey, rows, render);
              })
              .catch(() => {
                tbody.innerHTML = `<tr><td colspan="${columns}">Unable to load data</td></tr>`;
              });
          }

          function formatFinding(row) {
            const type = row.finding_type;
            const labelMap = {
              matched: 'Matched',
              amount_mismatch: 'Amount mismatch',
              missing_etims_purchase: 'Missing ETIMS purchase',
              missing_customs_support: 'Missing customs support'
            };
            const cls = type === 'matched' ? 'matched' : type.includes('missing') ? 'alert' : 'warning';
            const etims = Number(row.etims_taxable_amount || 0);
            const customs = Number(row.customs_value || 0);
            const variance = Math.abs(etims - customs);
            const risk = computeRiskScore(row);
            return `
              <td>${row.taxpayer_id}</td>
              <td>${row.event_date}</td>
              <td class="status ${cls}"><span class="finding-label">${labelMap[type] || type}</span></td>
              <td><span class="risk-pill ${cls}">${risk}/100</span></td>
              <td>${formatMoney(etims)}</td>
              <td>${formatMoney(customs)}</td>
              <td>${formatMoney(variance)}</td>
            `;
          }

          function formatDuplicate(row) {
            return `
              <td>${row.invoice_number}</td>
              <td>${row.occurrence_count}</td>
              <td>${row.buyer_taxpayer_ids ? row.buyer_taxpayer_ids.join(', ') : '-'}</td>
            `;
          }

          function formatGap(row) {
            return `
              <td>${row.buyer_taxpayer_id}</td>
              <td>${row.invoice_number}</td>
              <td>${row.invoice_date}</td>
              <td>${row.previous_invoice_date}</td>
              <td>${row.days_since_previous_invoice}</td>
            `;
          }

          function bindFilterButtons() {
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach((button) => {
              button.addEventListener('click', () => {
                buttons.forEach((btn) => btn.classList.toggle('active', btn === button));
                const filter = button.dataset.filter;
                fetch('/findings')
                  .then((response) => response.json())
                  .then((rows) => {
                    const enriched = rows.map((row) => ({ ...row, risk_score: computeRiskScore(row) }));
                    renderPriorityList(enriched);
                    renderExecutiveSummary(enriched);
                    renderFindingsTable(enriched, sortState.findings.key, sortState.findings.direction, filter);
                  })
                  .catch(() => {
                    document.getElementById('findings-body').innerHTML = '<tr><td colspan="7">Unable to load findings</td></tr>';
                  });
              });
            });
          }

          loadSummary();
          bindFilterButtons();
          bindTaxpayerSearch();

          const pageShell = document.querySelector('.page-shell');
          document.getElementById('print-report').addEventListener('click', () => window.print());
          document.getElementById('executive-toggle').addEventListener('click', () => {
            const isExecutive = pageShell.classList.toggle('executive-mode');
            document.getElementById('executive-toggle').textContent = isExecutive ? 'Detailed view' : 'Executive view';
          });

          refreshAdminSession().then(loadRiskResults);
          fetch('/findings')
            .then((response) => response.json())
            .then((rows) => {
              rows = rows.map((row) => ({ ...row, risk_score: computeRiskScore(row) }));
              renderPriorityList(rows);
              renderExecutiveSummary(rows);
              renderFindingsTable(rows, sortState.findings.key, sortState.findings.direction, 'anomaly');
              attachSortHandlers('findings', rows, (data, key, direction) => renderFindingsTable(data, key, direction, document.querySelector('.filter-btn.active')?.dataset.filter || 'anomaly'));
            });

          renderGenericTable('duplicates', '/duplicate-invoices', formatDuplicate, 3);
          renderGenericTable('gaps', '/timing-gaps', formatGap, 5);
        </script>
      </body>
    </html>
    """


@app.get("/summary")
def get_summary() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total_findings FROM audit.reconciliation_findings")
            total_findings = cur.fetchone()["total_findings"]

            cur.execute("SELECT COUNT(*) AS anomaly_findings FROM audit.reconciliation_findings WHERE finding_type <> 'matched'")
            anomaly_findings = cur.fetchone()["anomaly_findings"]

            cur.execute("SELECT COUNT(*) AS matched_findings FROM audit.reconciliation_findings WHERE finding_type = 'matched'")
            matched_findings = cur.fetchone()["matched_findings"]

            cur.execute("SELECT COUNT(*) AS total_duplicates FROM audit.duplicate_invoice_numbers")
            total_duplicates = cur.fetchone()["total_duplicates"]

            cur.execute("SELECT COUNT(*) AS total_timing_gaps FROM audit.invoice_timing_gaps")
            total_timing_gaps = cur.fetchone()["total_timing_gaps"]

            cur.execute("SELECT COUNT(*) AS total_taxpayers FROM core.taxpayer")
            total_taxpayers = cur.fetchone()["total_taxpayers"]

            cur.execute("SELECT COUNT(*) AS flagged_taxpayers FROM audit.risk_results WHERE risk_score > 0")
            flagged_taxpayers = cur.fetchone()["flagged_taxpayers"]

            cur.execute("SELECT COALESCE(SUM(variance), 0) AS total_sales_variance FROM audit.sales_mismatches")
            total_sales_variance = cur.fetchone()["total_sales_variance"]

    return {
        "total_findings": total_findings,
        "anomaly_findings": anomaly_findings,
        "matched_findings": matched_findings,
        "total_duplicates": total_duplicates,
        "total_timing_gaps": total_timing_gaps,
        "total_taxpayers": total_taxpayers,
        "flagged_taxpayers": flagged_taxpayers,
        "total_sales_variance": total_sales_variance,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            result = cur.fetchone()
    return {"status": "ok", "database": result}


@app.get("/findings")
def get_findings() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.reconciliation_findings ORDER BY taxpayer_id, event_date"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/taxpayers/search")
def search_taxpayers(q: str = "") -> list[dict[str, Any]]:
    query = """
        SELECT
            t.taxpayer_id,
            t.kra_pin,
            t.legal_name,
            COALESCE(s.recorded_sales, 0) AS recorded_sales,
            COALESCE(s.declared_sales, 0) AS declared_sales,
            COALESCE(s.sales_variance, 0) AS sales_variance,
            COALESCE(r.risk_score, 0) AS risk_score,
            COALESCE(r.risk_level, 'low') AS risk_level,
            COALESCE(r.review_status, 'pending') AS review_status,
            COALESCE(r.reason, 'No compliance indicator triggered') AS reason
        FROM core.taxpayer t
        LEFT JOIN (
            SELECT
                i.seller_taxpayer_id AS taxpayer_id,
                SUM(i.taxable_amount) AS recorded_sales,
                SUM(r.declared_sales) AS declared_sales,
                SUM(i.taxable_amount) - SUM(r.declared_sales) AS sales_variance
            FROM source.etims_invoice i
            JOIN source.tax_return r
              ON r.taxpayer_id = i.seller_taxpayer_id
             AND r.tax_period = DATE_TRUNC('month', i.invoice_date)::DATE
            GROUP BY i.seller_taxpayer_id
        ) s ON s.taxpayer_id = t.taxpayer_id
        LEFT JOIN audit.risk_results r ON r.taxpayer_id = t.taxpayer_id
        WHERE (%s = '' OR t.kra_pin ILIKE %s OR t.legal_name ILIKE %s)
        ORDER BY COALESCE(r.risk_score, 0) DESC, t.legal_name
        LIMIT 25
    """
    pattern = f"%{q}%"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (q, pattern, pattern))
            return cur.fetchall()


@app.get("/duplicate-invoices")
def get_duplicate_invoices() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.duplicate_invoice_numbers ORDER BY invoice_number"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/timing-gaps")
def get_timing_gaps() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.invoice_timing_gaps ORDER BY buyer_taxpayer_id, invoice_date"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

@app.get("/sales-mismatches")
def get_sales_mismatches() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.sales_mismatches ORDER BY taxpayer_id, tax_period"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.get("/risk-results")
def get_risk_results() -> list[dict[str, Any]]:
    query = "SELECT * FROM audit.risk_results ORDER BY risk_score DESC, taxpayer_id"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


@app.patch("/case-reviews/{taxpayer_id}")
def update_case_review(
  taxpayer_id: int,
  payload: dict[str, str] = Body(...),
  admin: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    status = payload.get("review_status", "pending")
    if status not in {"pending", "reviewed"}:
        raise HTTPException(status_code=400, detail="review_status must be pending or reviewed")

    comments = payload.get("reviewer_comments")
    query = """
        INSERT INTO audit.case_review (taxpayer_id, review_status, reviewer_comments)
        VALUES (%s, %s, %s)
        ON CONFLICT (taxpayer_id) DO UPDATE SET
            review_status = EXCLUDED.review_status,
            reviewer_comments = EXCLUDED.reviewer_comments,
            updated_at = now()
        RETURNING case_id, taxpayer_id, review_status, reviewer_comments, updated_at
    """
    with get_connection() as conn:
      with conn.cursor() as cur:
        cur.execute(
          "SELECT taxpayer_id FROM core.taxpayer WHERE taxpayer_id = %s FOR UPDATE",
          (taxpayer_id,),
        )
        if cur.fetchone() is None:
          raise HTTPException(status_code=404, detail="Taxpayer not found")
        cur.execute(
          "SELECT review_status, reviewer_comments FROM audit.case_review WHERE taxpayer_id = %s FOR UPDATE",
          (taxpayer_id,),
        )
        previous = cur.fetchone()
        cur.execute(query, (taxpayer_id, status, comments))
        updated = cur.fetchone()
        cur.execute(
          """INSERT INTO audit.admin_change_log
             (administrator_id, action, entity_type, entity_id, old_values, new_values)
             VALUES (%s, 'case_review.updated', 'case_review', %s, %s::jsonb, %s::jsonb)""",
          (
            admin["administrator_id"],
            str(taxpayer_id),
            json.dumps(previous),
            json.dumps({"review_status": updated["review_status"], "reviewer_comments": updated["reviewer_comments"]}),
          ),
        )
        return updated
