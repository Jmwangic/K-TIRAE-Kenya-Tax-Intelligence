import os
from decimal import Decimal

import psycopg
import pytest


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

        assert risk_score >= 70
        assert risk_level == "high"
        assert "Recorded sales exceed declared sales" in reason
        assert "Duplicate invoice numbers detected" in reason
