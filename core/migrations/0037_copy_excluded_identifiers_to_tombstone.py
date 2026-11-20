from django.db import connections, migrations

from core.db_router import TOMBSTONE_ALIAS

SOURCE_TABLE = "excluded_identifier"
DEFAULT_KIND = "ANONYMIZED"


def copy_to_tombstone(apps, schema_editor):
    source = connections["default"]
    if SOURCE_TABLE not in source.introspection.table_names():
        return
    with source.cursor() as cursor:
        columns = {
            column.name for column in source.introspection.get_table_description(cursor, SOURCE_TABLE)
        }
        kind_select = "kind" if "kind" in columns else f"'{DEFAULT_KIND}'"
        cursor.execute(f"SELECT identifier_hash, {kind_select}, created_at FROM {SOURCE_TABLE}")
        rows = cursor.fetchall()
    ExcludedIdentifier = apps.get_model("core", "ExcludedIdentifier")
    ExcludedIdentifier.objects.using(TOMBSTONE_ALIAS).bulk_create(
        [
            ExcludedIdentifier(identifier_hash=identifier_hash, kind=kind, created_at=created_at)
            for identifier_hash, kind, created_at in rows
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0035_merge_subject_notification_and_revision_decision_notifications")]

    operations = [
        migrations.RunPython(
            copy_to_tombstone,
            migrations.RunPython.noop,
            hints={"tombstone_copy": True},
        ),
    ]
