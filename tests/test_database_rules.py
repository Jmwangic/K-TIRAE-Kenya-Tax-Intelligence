import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/kra_anomaly",
)


@pytest.fixture
def connection():
    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as exc:
        pytest.fail(f"Could not connect to the test database: {exc}")

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('audit.sales_mismatches')")
            if cur.fetchone()[0] is None:
                pytest.fail("Database is not bootstrapped; run scripts/bootstrap_local_db.ps1 first")
        yield conn
        conn.rollback()

    conn.close()


def insert_taxpayer(cur, pin_suffix: str) -> int:
    cur.execute(
        """
        INSERT INTO core.taxpayer (kra_pin, legal_name, industry_code)
        VALUES (%s, %s, 'TEST')
        RETURNING taxpayer_id
        """,
        (f"TEST{pin_suffix}", f"Test Taxpayer {pin_suffix}"),
    )
    return cur.fetchone()[0]


def insert_return(cur, taxpayer_id: int, declared_sales: Decimal) -> None:
    cur.execute(
        """
        INSERT INTO source.tax_return (
            taxpayer_id, tax_period, declared_sales, declared_purchases, output_vat, input_vat
        )
        VALUES (%s, DATE '2026-06-01', %s, 100.00, 0.00, 0.00)
        """,
        (taxpayer_id, declared_sales),
    )


def insert_invoice(cur, number: str, seller_id: int, buyer_id: int, amount: Decimal) -> None:
    cur.execute(
        """
        INSERT INTO source.etims_invoice (
            invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date,
            taxable_amount, output_vat, item_description
        )
        VALUES (%s, %s, %s, DATE '2026-06-15', %s, 0.00, 'Test item')
        """,
        (number, seller_id, buyer_id, amount),
    )


def test_sales_mismatch_normal_and_boundary_cases_are_not_flagged(connection):
    with connection.cursor() as cur:
        buyer_id = insert_taxpayer(cur, "NORMAL")
        boundary_id = insert_taxpayer(cur, "BOUNDARY")
        normal_id = insert_taxpayer(cur, "MATCHED")
        insert_return(cur, buyer_id, Decimal("100.00"))
        insert_return(cur, boundary_id, Decimal("100.00"))
        insert_return(cur, normal_id, Decimal("100.00"))
        insert_invoice(cur, "TEST-NORMAL", buyer_id, normal_id, Decimal("100.00"))
        insert_invoice(cur, "TEST-BOUNDARY", boundary_id, normal_id, Decimal("120.00"))

        cur.execute(
            """
            SELECT taxpayer_id, variance
            FROM audit.sales_mismatches
            WHERE taxpayer_id IN (%s, %s)
            """,
            (buyer_id, boundary_id),
        )

        assert cur.fetchall() == []


def test_sales_mismatch_flags_amounts_above_threshold(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "MISMATCH")
        buyer_id = insert_taxpayer(cur, "MISMATCHBUYER")
        insert_return(cur, seller_id, Decimal("100.00"))
        insert_invoice(cur, "TEST-MISMATCH", seller_id, buyer_id, Decimal("121.00"))

        cur.execute(
            """
            SELECT variance, variance_percent
            FROM audit.sales_mismatches
            WHERE taxpayer_id = %s
            """,
            (seller_id,),
        )

        assert cur.fetchone() == (Decimal("21.00"), Decimal("21.00"))


def test_duplicate_invoice_and_risk_result_are_explainable(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "RISKSELLER")
        second_seller_id = insert_taxpayer(cur, "RISKSELLER2")
        buyer_id = insert_taxpayer(cur, "RISKBUYER")
        second_buyer_id = insert_taxpayer(cur, "RISKBUYER2")
        insert_return(cur, seller_id, Decimal("100.00"))
        insert_invoice(cur, "TEST-DUPLICATE", seller_id, buyer_id, Decimal("121.00"))
        insert_invoice(cur, "TEST-DUPLICATE", second_seller_id, second_buyer_id, Decimal("50.00"))

        cur.execute(
            """
            SELECT invoice_number
            FROM audit.duplicate_invoice_numbers
            WHERE invoice_number = 'TEST-DUPLICATE'
            """
        )
        assert cur.fetchone() == ("TEST-DUPLICATE",)

        cur.execute(
            """
            SELECT risk_score, risk_level, reason
            FROM audit.risk_results
            WHERE taxpayer_id = %s
            """,
            (seller_id,),
        )
        risk_score, risk_level, reason = cur.fetchone()

        assert risk_score == 80
        assert risk_level == "high"
        assert "Recorded sales exceed declared sales" in reason
        assert "Duplicate invoice numbers detected" in reason


def test_admin_change_history_rejects_update_and_delete(connection):
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO core.administrator (username, password_hash) VALUES (%s, %s) RETURNING administrator_id",
            (f"audit-{uuid4().hex}", "test-hash"),
        )
        administrator_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO audit.admin_change_log
               (administrator_id, action, entity_type, entity_id)
               VALUES (%s, 'test', 'test_record', '1') RETURNING log_id""",
            (administrator_id,),
        )
        log_id = cur.fetchone()[0]

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cur.execute("UPDATE audit.admin_change_log SET action = 'tampered' WHERE log_id = %s", (log_id,))
        connection.rollback()

        with connection.cursor() as retry_cur:
            retry_cur.execute(
                """INSERT INTO core.administrator (username, password_hash)
                   VALUES (%s, %s) RETURNING administrator_id""",
                (f"audit-delete-{uuid4().hex}", "test-hash"),
            )
            delete_admin_id = retry_cur.fetchone()[0]
            retry_cur.execute(
                """INSERT INTO audit.admin_change_log
                   (administrator_id, action, entity_type, entity_id)
                   VALUES (%s, 'test', 'test_record', '2') RETURNING log_id""",
                (delete_admin_id,),
            )
            delete_log_id = retry_cur.fetchone()[0]
            with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
                retry_cur.execute("DELETE FROM audit.admin_change_log WHERE log_id = %s", (delete_log_id,))


def test_reapplying_all_migrations_preserves_existing_data(connection):
    pin = f"PRESERVE{uuid4().hex}"
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO core.taxpayer (kra_pin, legal_name) VALUES (%s, %s) RETURNING taxpayer_id",
            (pin, "Preserved taxpayer"),
        )
        taxpayer_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE source.tax_return SET declared_sales = 54321.00 "
            "WHERE taxpayer_id = 1 AND tax_period = DATE '2026-01-01'"
        )
        assert cur.rowcount == 1

    migration_dir = Path(__file__).resolve().parents[1] / "db"
    for migration in sorted(migration_dir.glob("*.sql")):
        connection.execute(migration.read_text(encoding="utf-8"))

    with connection.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM core.taxpayer WHERE taxpayer_id = %s)", (taxpayer_id,))
        assert cur.fetchone()[0]
        cur.execute(
            "SELECT declared_sales FROM source.tax_return "
            "WHERE taxpayer_id = 1 AND tax_period = DATE '2026-01-01'"
        )
        assert cur.fetchone()[0] == Decimal("54321.00")


def test_invoice_rejects_negative_amounts_and_unknown_taxpayers(connection):
    with connection.cursor() as cur:
        buyer_id = insert_taxpayer(cur, "INVALIDINVOICEBUYER")
        seller_id = insert_taxpayer(cur, "INVALIDINVOICER")
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_invoice(cur, "TEST-NEGATIVE", seller_id, buyer_id, Decimal("-1.00"))

    connection.rollback()
    with connection.cursor() as cur:
        buyer_id = insert_taxpayer(cur, "UNKNOWNSELLERBUYER")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            insert_invoice(cur, "TEST-UNKNOWN-SELLER", 999999999, buyer_id, Decimal("10.00"))


def test_source_tables_reject_duplicate_and_invalid_records(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "SOURCESELLER")
        buyer_id = insert_taxpayer(cur, "SOURCEBUYER")
        payer_id = insert_taxpayer(cur, "SOURCEPAYER")
        payee_id = insert_taxpayer(cur, "SOURCEPAYEE")
        insert_invoice(cur, "TEST-SOURCE-DUPLICATE", seller_id, buyer_id, Decimal("10.00"))

        with pytest.raises(psycopg.errors.UniqueViolation):
            with connection.transaction():
                insert_invoice(cur, "TEST-SOURCE-DUPLICATE", seller_id, buyer_id, Decimal("20.00"))

        with pytest.raises(psycopg.errors.NotNullViolation):
            with connection.transaction():
                cur.execute(
                    """INSERT INTO source.etims_invoice (
                           invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date,
                           taxable_amount, output_vat, item_description
                       ) VALUES (NULL, %s, %s, DATE '2026-06-15', 10.00, 0.00, 'Test')""",
                    (seller_id, buyer_id),
                )

        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                cur.execute(
                    """INSERT INTO source.customs_import (
                           import_entry_number, importer_taxpayer_id, declaration_date,
                           customs_value, import_vat, item_description
                       ) VALUES ('TEST-NEGATIVE-CUSTOMS', %s, DATE '2026-06-15', -1.00, 0.00, 'Test')""",
                    (buyer_id,),
                )

        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                cur.execute(
                    """INSERT INTO source.withholding_tax (
                           certificate_number, payer_taxpayer_id, payee_taxpayer_id,
                           payment_date, gross_amount, tax_withheld
                       ) VALUES ('TEST-NEGATIVE-WHT', %s, %s, DATE '2026-06-15', 10.00, -1.00)""",
                    (payer_id, payee_id),
                )


def test_tax_return_rejects_negative_declared_sales(connection):
    with connection.cursor() as cur:
        taxpayer_id = insert_taxpayer(cur, "NEGATIVERETURN")
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                """INSERT INTO source.tax_return (
                       taxpayer_id, tax_period, declared_sales, declared_purchases, output_vat, input_vat
                   ) VALUES (%s, DATE '2026-06-01', -1.00, 0.00, 0.00, 0.00)""",
                (taxpayer_id,),
            )


def test_input_vat_quality_rule_uses_strict_18_percent_boundary(connection):
    with connection.cursor() as cur:
        at_boundary_id = insert_taxpayer(cur, "VATBOUNDARY")
        above_boundary_id = insert_taxpayer(cur, "VATOVER")
        cur.execute(
            """INSERT INTO source.tax_return (
                   taxpayer_id, tax_period, declared_sales, declared_purchases, output_vat, input_vat
               ) VALUES
                   (%s, DATE '2026-06-01', 0.00, 100.00, 0.00, 18.00),
                   (%s, DATE '2026-06-01', 0.00, 100.00, 0.00, 18.01)""",
            (at_boundary_id, above_boundary_id),
        )
        cur.execute(
            "SELECT taxpayer_id FROM audit.data_quality_findings "
            "WHERE taxpayer_id IN (%s, %s) AND finding_type = 'tax_return_input_vat_exceeds_purchases'",
            (at_boundary_id, above_boundary_id),
        )

        assert cur.fetchall() == [(above_boundary_id,)]


def test_invoice_timing_gap_rule_excludes_30_days_and_flags_31(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "GAPSELLER")
        buyer_id = insert_taxpayer(cur, "GAPBUYER")
        cur.execute(
            """INSERT INTO source.etims_invoice (
                   invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date,
                   taxable_amount, output_vat, item_description
               ) VALUES
                   ('TEST-GAP-1', %s, %s, DATE '2026-01-01', 10.00, 0.00, 'Test'),
                   ('TEST-GAP-30', %s, %s, DATE '2026-01-31', 10.00, 0.00, 'Test'),
                   ('TEST-GAP-31', %s, %s, DATE '2026-03-03', 10.00, 0.00, 'Test')""",
            (seller_id, buyer_id, seller_id, buyer_id, seller_id, buyer_id),
        )
        cur.execute(
            "SELECT invoice_number, days_since_previous_invoice FROM audit.invoice_timing_gaps "
            "WHERE buyer_taxpayer_id = %s",
            (buyer_id,),
        )

        assert cur.fetchall() == [("TEST-GAP-31", 31)]


def test_reconciliation_includes_unmatched_etims_and_customs_records(connection):
    with connection.cursor() as cur:
        etims_only_id = insert_taxpayer(cur, "ETIMSONLY")
        customs_only_id = insert_taxpayer(cur, "CUSTOMSONLY")
        seller_id = insert_taxpayer(cur, "UNMATCHEDSELLER")
        insert_invoice(cur, "TEST-ETIMS-ONLY", seller_id, etims_only_id, Decimal("50.00"))
        cur.execute(
            """INSERT INTO source.customs_import (
                   import_entry_number, importer_taxpayer_id, declaration_date,
                   customs_value, import_vat, item_description
               ) VALUES ('TEST-CUSTOMS-ONLY', %s, DATE '2026-06-15', 75.00, 0.00, 'Test')""",
            (customs_only_id,),
        )
        cur.execute(
            "SELECT taxpayer_id, finding_type FROM audit.reconciliation_findings "
            "WHERE taxpayer_id IN (%s, %s) AND event_date = DATE '2026-06-15' ORDER BY taxpayer_id",
            (etims_only_id, customs_only_id),
        )

        assert cur.fetchall() == [
            (etims_only_id, "missing_customs_support"),
            (customs_only_id, "missing_etims_purchase"),
        ]


def test_risk_result_aggregates_indicators_into_medium_score(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "RISKMEDIUM")
        buyer_id = insert_taxpayer(cur, "RISKMEDIUMBUYER")
        insert_return(cur, seller_id, Decimal("100.00"))
        cur.execute(
            "UPDATE source.tax_return SET declared_purchases = 100.00, input_vat = 19.00 "
            "WHERE taxpayer_id = %s AND tax_period = DATE '2026-06-01'",
            (seller_id,),
        )
        insert_invoice(cur, "TEST-RISK-MEDIUM", seller_id, buyer_id, Decimal("121.00"))
        cur.execute(
            "SELECT risk_score, risk_level FROM audit.risk_results WHERE taxpayer_id = %s",
            (seller_id,),
        )

        assert cur.fetchone() == (50, "medium")


def test_risk_score_is_capped_at_100(connection):
    with connection.cursor() as cur:
        seller_id = insert_taxpayer(cur, "RISKCAPSELLER")
        buyer_id = insert_taxpayer(cur, "RISKCAPBUYER")
        periods = ["2026-01-01", "2026-02-01", "2026-03-01"]
        cur.executemany(
            """INSERT INTO source.tax_return (
                   taxpayer_id, tax_period, declared_sales, declared_purchases, output_vat, input_vat
               ) VALUES (%s, %s::date, 100.00, 100.00, 0.00, 0.00)""",
            [(seller_id, period) for period in periods],
        )
        cur.executemany(
            """INSERT INTO source.etims_invoice (
                   invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date,
                   taxable_amount, output_vat, item_description
               ) VALUES (%s, %s, %s, %s::date, 121.00, 0.00, 'Test')""",
            [
                (f"TEST-RISK-CAP-{index}", seller_id, buyer_id, f"2026-0{index}-15")
                for index in range(1, 4)
            ],
        )
        cur.execute(
            "SELECT risk_score, risk_level FROM audit.risk_results WHERE taxpayer_id = %s",
            (seller_id,),
        )

        assert cur.fetchone() == (100, "high")


def test_dashboard_read_routes_return_seed_contract(connection):
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "database": {"ok": 1}}

    summary = client.get("/summary")
    assert summary.status_code == 200
    assert summary.json()["total_taxpayers"] == 3
    assert summary.json()["total_findings"] == 4

    for route in (
        "/findings",
        "/duplicate-invoices",
        "/timing-gaps",
        "/sales-mismatches",
        "/risk-results",
        "/invoices",
        "/taxpayers/search?q=Northstar",
    ):
        response = client.get(route)
        assert response.status_code == 200, route
        assert isinstance(response.json(), list), route

    search = client.get("/taxpayers/search", params={"q": "Northstar"})
    assert [taxpayer["kra_pin"] for taxpayer in search.json()] == ["P000200002B"]
