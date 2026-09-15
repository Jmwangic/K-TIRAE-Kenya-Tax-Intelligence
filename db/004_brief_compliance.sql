CREATE TABLE IF NOT EXISTS source.tax_return (
    return_id BIGSERIAL PRIMARY KEY,
    taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    tax_period DATE NOT NULL,
    declared_sales NUMERIC(18, 2) NOT NULL CHECK (declared_sales >= 0),
    declared_purchases NUMERIC(18, 2) NOT NULL CHECK (declared_purchases >= 0),
    output_vat NUMERIC(18, 2) NOT NULL CHECK (output_vat >= 0),
    input_vat NUMERIC(18, 2) NOT NULL CHECK (input_vat >= 0),
    UNIQUE (taxpayer_id, tax_period)
);

CREATE TABLE IF NOT EXISTS audit.case_review (
    case_id BIGSERIAL PRIMARY KEY,
    taxpayer_id BIGINT NOT NULL UNIQUE REFERENCES core.taxpayer(taxpayer_id),
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'reviewed')),
    reviewer_comments TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tax_return_taxpayer_period
    ON source.tax_return (taxpayer_id, tax_period);

INSERT INTO source.tax_return (
    taxpayer_id, tax_period, declared_sales, declared_purchases, output_vat, input_vat
)
VALUES
    (1, DATE '2026-01-01', 100000.00, 80000.00, 16000.00, 12800.00),
    (1, DATE '2026-03-01', 125000.00, 90000.00, 20000.00, 14400.00),
    (2, DATE '2026-03-01', 50000.00, 40000.00, 8000.00, 6400.00),
    (3, DATE '2026-03-01', 125000.00, 90000.00, 20000.00, 14400.00)
ON CONFLICT (taxpayer_id, tax_period) DO UPDATE SET
    declared_sales = EXCLUDED.declared_sales,
    declared_purchases = EXCLUDED.declared_purchases,
    output_vat = EXCLUDED.output_vat,
    input_vat = EXCLUDED.input_vat;

CREATE OR REPLACE VIEW audit.sales_mismatches AS
SELECT
    i.seller_taxpayer_id AS taxpayer_id,
    DATE_TRUNC('month', i.invoice_date)::DATE AS tax_period,
    SUM(i.taxable_amount) AS recorded_sales,
    r.declared_sales,
    SUM(i.taxable_amount) - r.declared_sales AS variance,
    ROUND((SUM(i.taxable_amount) - r.declared_sales) / NULLIF(r.declared_sales, 0) * 100, 2) AS variance_percent
FROM source.etims_invoice i
JOIN source.tax_return r
  ON r.taxpayer_id = i.seller_taxpayer_id
 AND r.tax_period = DATE_TRUNC('month', i.invoice_date)::DATE
GROUP BY i.seller_taxpayer_id, DATE_TRUNC('month', i.invoice_date)::DATE, r.declared_sales
HAVING SUM(i.taxable_amount) > r.declared_sales * 1.20;

CREATE OR REPLACE VIEW audit.data_quality_findings AS
SELECT taxpayer_id, 'tax_return_input_vat_exceeds_purchases' AS finding_type,
       'Input VAT exceeds 18% of declared purchases' AS explanation
FROM source.tax_return
WHERE declared_purchases > 0 AND input_vat / declared_purchases > 0.18
UNION ALL
SELECT seller_taxpayer_id, 'duplicate_invoice_number' AS finding_type,
       'Invoice number appears for more than one buyer' AS explanation
FROM source.etims_invoice
GROUP BY seller_taxpayer_id
HAVING COUNT(*) FILTER (WHERE invoice_number IN (
    SELECT invoice_number FROM source.etims_invoice GROUP BY invoice_number HAVING COUNT(*) > 1
)) > 0;

CREATE OR REPLACE VIEW audit.risk_results AS
WITH sales AS (
    SELECT taxpayer_id, COUNT(*) * 40 AS points,
           STRING_AGG(format('Recorded sales exceed declared sales by %s%% in %s', variance_percent, tax_period), '; ') AS reason
    FROM audit.sales_mismatches
    GROUP BY taxpayer_id
), duplicates AS (
    SELECT seller_taxpayer_id AS taxpayer_id, COUNT(*) * 30 AS points,
           'Duplicate invoice numbers detected' AS reason
    FROM source.etims_invoice
    WHERE invoice_number IN (
        SELECT invoice_number FROM source.etims_invoice GROUP BY invoice_number HAVING COUNT(*) > 1
    )
    GROUP BY seller_taxpayer_id
), quality AS (
    SELECT taxpayer_id, COUNT(*) * 10 AS points,
           STRING_AGG(explanation, '; ') AS reason
    FROM audit.data_quality_findings
    GROUP BY taxpayer_id
), scores AS (
    SELECT t.taxpayer_id,
           LEAST(100, COALESCE(s.points, 0) + COALESCE(d.points, 0) + COALESCE(q.points, 0)) AS risk_score,
           CONCAT_WS('; ', s.reason, d.reason, q.reason) AS reason
    FROM core.taxpayer t
    LEFT JOIN sales s ON s.taxpayer_id = t.taxpayer_id
    LEFT JOIN duplicates d ON d.taxpayer_id = t.taxpayer_id
    LEFT JOIN quality q ON q.taxpayer_id = t.taxpayer_id
)
SELECT
    scores.taxpayer_id,
    scores.risk_score,
    CASE WHEN scores.risk_score >= 51 THEN 'high'
         WHEN scores.risk_score >= 21 THEN 'medium'
         ELSE 'low' END AS risk_level,
    COALESCE(NULLIF(scores.reason, ''), 'No compliance indicator triggered') AS reason,
    COALESCE(c.review_status, 'pending') AS review_status,
    c.reviewer_comments
FROM scores
LEFT JOIN audit.case_review c ON c.taxpayer_id = scores.taxpayer_id;
