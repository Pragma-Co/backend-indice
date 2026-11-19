from django.db import connections, migrations

from core.db_router import TOMBSTONE_ALIAS

SOURCE_TABLE = "excluded_identifier"


def copy_to_tombstone(apps, schema_editor):
    source = connections["default"]
    if SOURCE_TABLE not in source.introspection.table_names():
        return
    with source.cursor() as cursor:
        cursor.execute(f"SELECT identifier_hash, created_at FROM {SOURCE_TABLE}")
        rows = cursor.fetchall()
    ExcludedIdentifier = apps.get_model("core", "ExcludedIdentifier")
    ExcludedIdentifier.objects.using(TOMBSTONE_ALIAS).bulk_create(
        [ExcludedIdentifier(identifier_hash=h, created_at=created_at) for h, created_at in rows],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0031_document_access_group")]

    operations = [
        migrations.RunPython(
            copy_to_tombstone,
            migrations.RunPython.noop,
            hints={"tombstone_copy": True},
        ),
    ]
