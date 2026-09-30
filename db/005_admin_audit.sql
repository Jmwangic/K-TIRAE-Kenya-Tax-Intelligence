CREATE TABLE IF NOT EXISTS core.administrator (
    administrator_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 1 AND 80),
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.admin_change_log (
    log_id BIGSERIAL PRIMARY KEY,
    administrator_id BIGINT NOT NULL REFERENCES core.administrator(administrator_id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_change_log_changed_at
    ON audit.admin_change_log (changed_at DESC, log_id DESC);

CREATE OR REPLACE FUNCTION audit.reject_change_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'administrator change history is append-only';
END;
$$;

DROP TRIGGER IF EXISTS admin_change_log_no_update ON audit.admin_change_log;
CREATE TRIGGER admin_change_log_no_update
    BEFORE UPDATE OR DELETE ON audit.admin_change_log
    FOR EACH ROW EXECUTE FUNCTION audit.reject_change_log_mutation();

DROP TRIGGER IF EXISTS admin_change_log_no_truncate ON audit.admin_change_log;
CREATE TRIGGER admin_change_log_no_truncate
    BEFORE TRUNCATE ON audit.admin_change_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_change_log_mutation();