"""Database-enforced behaviour that the ORM cannot express.

1. `document.updated_at` is maintained by a trigger, not by the application,
   so a bulk UPDATE or a raw statement cannot leave it stale.
2. `audit_log` is append-only.

The model document suggests making the audit trail append-only by revoking
UPDATE/DELETE from the application role. That has no effect here: in the
Docker setup the application connects as POSTGRES_USER, which is a superuser
and therefore bypasses every privilege check. A trigger holds regardless of
the role, so it is used instead. If a dedicated non-superuser role is created
later, the REVOKE becomes a useful second layer — not a replacement.
"""

from django.db import migrations

CREATE_SET_UPDATED_AT = """
    CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql
    AS $func$
    BEGIN
        NEW.updated_at := now();
        RETURN NEW;
    END
    $func$;

    CREATE TRIGGER document_set_updated_at
        BEFORE UPDATE ON document
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

DROP_SET_UPDATED_AT = """
    DROP TRIGGER IF EXISTS document_set_updated_at ON document;
    DROP FUNCTION IF EXISTS set_updated_at();
"""

CREATE_AUDIT_APPEND_ONLY = """
    CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger
        LANGUAGE plpgsql
    AS $func$
    BEGIN
        -- One exception: the ON DELETE SET NULL on audit_log.user_id, which
        -- PostgreSQL carries out as an UPDATE when an app_user row is
        -- deleted. Everything else about the row must stay untouched.
        IF TG_OP = 'UPDATE'
           AND OLD.user_id IS NOT NULL
           AND NEW.user_id IS NULL
           AND NEW.id = OLD.id
           AND NEW.occurred_at = OLD.occurred_at
           AND NEW.action = OLD.action
           AND NEW.entity = OLD.entity
           AND NEW.entity_id IS NOT DISTINCT FROM OLD.entity_id
           AND NEW.record IS NOT DISTINCT FROM OLD.record
           AND NEW.ip_address IS NOT DISTINCT FROM OLD.ip_address
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'audit_log is append-only: only INSERT and SELECT are allowed'
            USING ERRCODE = 'restrict_violation';
    END
    $func$;

    CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
"""

DROP_AUDIT_APPEND_ONLY = """
    DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log;
    DROP FUNCTION IF EXISTS audit_log_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_SET_UPDATED_AT, reverse_sql=DROP_SET_UPDATED_AT
        ),
        migrations.RunSQL(
            sql=CREATE_AUDIT_APPEND_ONLY, reverse_sql=DROP_AUDIT_APPEND_ONLY
        ),
    ]
