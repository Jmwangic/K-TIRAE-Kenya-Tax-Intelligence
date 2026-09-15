TRUNCATE TABLE
    source.withholding_tax,
    source.customs_import,
    source.etims_invoice,
    core.taxpayer
RESTART IDENTITY CASCADE;

INSERT INTO core.taxpayer (kra_pin, legal_name, industry_code)
VALUES
    ('P000100001A', 'Acme Retail Ltd', 'G4711'),
    ('P000200002B', 'Northstar Imports Ltd', 'G4690'),
    ('P000300003C', 'Transit Supplies Ltd', 'G4690');

INSERT INTO source.etims_invoice (
    invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date,
    taxable_amount, output_vat, item_description
)
SELECT * FROM (VALUES
    ('INV-1001', 2, 1, DATE '2026-01-10', 100000.00, 16000.00, 'Imported electronics'),
    ('INV-1002', 3, 1, DATE '2026-03-01', 125000.00, 20000.00, 'Imported electronics'),
    ('INV-1002', 2, 2, DATE '2026-03-02', 125000.00, 20000.00, 'Imported electronics')
) AS seed(invoice_number, seller_taxpayer_id, buyer_taxpayer_id, invoice_date, taxable_amount, output_vat, item_description);

INSERT INTO source.customs_import (
    import_entry_number, importer_taxpayer_id, declaration_date,
    customs_value, import_vat, item_description
)
VALUES
    ('CUS-9001', 1, DATE '2026-01-10', 100000.00, 16000.00, 'Imported electronics'),
    ('CUS-9002', 1, DATE '2026-03-01', 1000.00, 160.00, 'Imported electronics');

INSERT INTO source.withholding_tax (
    certificate_number, payer_taxpayer_id, payee_taxpayer_id,
    payment_date, gross_amount, tax_withheld
)
VALUES
    ('WHT-7001', 1, 2, DATE '2026-01-10', 100000.00, 5000.00);
