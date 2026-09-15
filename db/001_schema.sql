CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS source;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS core.taxpayer (
    taxpayer_id BIGSERIAL PRIMARY KEY,
    kra_pin TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    industry_code TEXT,
    registered_latitude NUMERIC(9, 6),
    registered_longitude NUMERIC(9, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source.etims_invoice (
    invoice_id BIGSERIAL PRIMARY KEY,
    invoice_number TEXT NOT NULL,
    seller_taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    buyer_taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    invoice_date DATE NOT NULL,
    taxable_amount NUMERIC(18, 2) NOT NULL CHECK (taxable_amount >= 0),
    output_vat NUMERIC(18, 2) NOT NULL CHECK (output_vat >= 0),
    item_description TEXT NOT NULL,
    source_hash TEXT,
    UNIQUE (seller_taxpayer_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS source.customs_import (
    import_id BIGSERIAL PRIMARY KEY,
    import_entry_number TEXT NOT NULL UNIQUE,
    importer_taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    declaration_date DATE NOT NULL,
    customs_value NUMERIC(18, 2) NOT NULL CHECK (customs_value >= 0),
    import_vat NUMERIC(18, 2) NOT NULL CHECK (import_vat >= 0),
    item_description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source.withholding_tax (
    withholding_id BIGSERIAL PRIMARY KEY,
    certificate_number TEXT NOT NULL UNIQUE,
    payer_taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    payee_taxpayer_id BIGINT NOT NULL REFERENCES core.taxpayer(taxpayer_id),
    payment_date DATE NOT NULL,
    gross_amount NUMERIC(18, 2) NOT NULL CHECK (gross_amount >= 0),
    tax_withheld NUMERIC(18, 2) NOT NULL CHECK (tax_withheld >= 0)
);

CREATE INDEX IF NOT EXISTS idx_etims_buyer_date
    ON source.etims_invoice (buyer_taxpayer_id, invoice_date);
CREATE INDEX IF NOT EXISTS idx_etims_invoice_number
    ON source.etims_invoice (invoice_number);
CREATE INDEX IF NOT EXISTS idx_customs_importer_date
    ON source.customs_import (importer_taxpayer_id, declaration_date);
