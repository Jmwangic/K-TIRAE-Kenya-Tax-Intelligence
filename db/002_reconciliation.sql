CREATE OR REPLACE VIEW audit.reconciliation_findings AS
WITH invoice_totals AS (
    SELECT
        buyer_taxpayer_id AS taxpayer_id,
        invoice_date AS event_date,
        COUNT(*) AS etims_invoice_count,
        SUM(taxable_amount) AS etims_taxable_amount,
        SUM(output_vat) AS etims_input_vat
    FROM source.etims_invoice
    GROUP BY buyer_taxpayer_id, invoice_date
), import_totals AS (
    SELECT
        importer_taxpayer_id AS taxpayer_id,
        declaration_date AS event_date,
        COUNT(*) AS customs_import_count,
        SUM(customs_value) AS customs_value,
        SUM(import_vat) AS customs_input_vat
    FROM source.customs_import
    GROUP BY importer_taxpayer_id, declaration_date
), withholding_totals AS (
    SELECT
        payee_taxpayer_id AS taxpayer_id,
        payment_date AS event_date,
        COUNT(*) AS withholding_count,
        SUM(gross_amount) AS withholding_gross_amount,
        SUM(tax_withheld) AS tax_withheld
    FROM source.withholding_tax
    GROUP BY payee_taxpayer_id, payment_date
)
SELECT
    COALESCE(i.taxpayer_id, c.taxpayer_id, w.taxpayer_id) AS taxpayer_id,
    COALESCE(i.event_date, c.event_date, w.event_date) AS event_date,
    COALESCE(i.etims_invoice_count, 0) AS etims_invoice_count,
    COALESCE(i.etims_taxable_amount, 0) AS etims_taxable_amount,
    COALESCE(i.etims_input_vat, 0) AS etims_input_vat,
    COALESCE(c.customs_import_count, 0) AS customs_import_count,
    COALESCE(c.customs_value, 0) AS customs_value,
    COALESCE(c.customs_input_vat, 0) AS customs_input_vat,
    COALESCE(w.withholding_count, 0) AS withholding_count,
    COALESCE(w.withholding_gross_amount, 0) AS withholding_gross_amount,
    COALESCE(w.tax_withheld, 0) AS tax_withheld,
    CASE
        WHEN i.taxpayer_id IS NULL THEN 'missing_etims_purchase'
        WHEN c.taxpayer_id IS NULL AND i.etims_taxable_amount > 0 THEN 'missing_customs_support'
        WHEN ABS(i.etims_taxable_amount - c.customs_value) > 0.01 THEN 'amount_mismatch'
        ELSE 'matched'
    END AS finding_type
FROM invoice_totals i
FULL OUTER JOIN import_totals c
    ON c.taxpayer_id = i.taxpayer_id
   AND c.event_date = i.event_date
FULL OUTER JOIN withholding_totals w
    ON w.taxpayer_id = COALESCE(i.taxpayer_id, c.taxpayer_id)
   AND w.event_date = COALESCE(i.event_date, c.event_date);

CREATE OR REPLACE VIEW audit.duplicate_invoice_numbers AS
SELECT
    invoice_number,
    COUNT(*) AS occurrence_count,
    COUNT(DISTINCT buyer_taxpayer_id) AS buyer_count,
    ARRAY_AGG(DISTINCT buyer_taxpayer_id ORDER BY buyer_taxpayer_id) AS buyer_taxpayer_ids
FROM source.etims_invoice
GROUP BY invoice_number
HAVING COUNT(DISTINCT buyer_taxpayer_id) > 1;

CREATE OR REPLACE VIEW audit.invoice_timing_gaps AS
WITH buyer_invoices AS (
    SELECT
        buyer_taxpayer_id,
        invoice_number,
        invoice_date,
        LAG(invoice_date) OVER (
            PARTITION BY buyer_taxpayer_id
            ORDER BY invoice_date, invoice_id
        ) AS previous_invoice_date
    FROM source.etims_invoice
)
SELECT
    buyer_taxpayer_id,
    invoice_number,
    invoice_date,
    previous_invoice_date,
    invoice_date - previous_invoice_date AS days_since_previous_invoice
FROM buyer_invoices
WHERE previous_invoice_date IS NOT NULL
  AND invoice_date - previous_invoice_date > 30;
