-- Organization-scoped logging upgrade.
-- Run this once in PostgreSQL if you do not rely on the startup compatibility
-- code in database.ensure_metadata_schema().

CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

INSERT INTO organizations (id, name, created_at)
VALUES (1, 'Default Organization', NOW())
ON CONFLICT (id) DO NOTHING;

ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user';

UPDATE users SET organization_id = COALESCE(organization_id, 1);
UPDATE users SET role = COALESCE(role, 'user');
ALTER TABLE users ALTER COLUMN role SET NOT NULL;

ALTER TABLE execution_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL;
ALTER TABLE execution_logs ADD COLUMN IF NOT EXISTS service_name VARCHAR(255);

ALTER TABLE error_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL;
ALTER TABLE error_logs ADD COLUMN IF NOT EXISTS service_name VARCHAR(255);
ALTER TABLE error_logs ADD COLUMN IF NOT EXISTS exception_type VARCHAR(255);
ALTER TABLE error_logs ADD COLUMN IF NOT EXISTS function_name VARCHAR(255);

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL;

UPDATE execution_logs AS log
SET organization_id = users.organization_id
FROM users
WHERE log.organization_id IS NULL
  AND log.user_id = users.id;

UPDATE error_logs AS log
SET organization_id = users.organization_id
FROM users
WHERE log.organization_id IS NULL
  AND log.user_id = users.id;

UPDATE audit_logs AS log
SET organization_id = users.organization_id
FROM users
WHERE log.organization_id IS NULL
  AND log.user_id = users.id;

CREATE INDEX IF NOT EXISTS ix_execution_logs_org_created ON execution_logs (organization_id, created_at);
CREATE INDEX IF NOT EXISTS ix_execution_logs_org_status_created ON execution_logs (organization_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_execution_logs_org_operation_created ON execution_logs (organization_id, operation_type, created_at);
CREATE INDEX IF NOT EXISTS ix_error_logs_org_created ON error_logs (organization_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_org_created ON audit_logs (organization_id, created_at);
