"""Recreate ``ck_file_extension`` on databases migrated before the enum changed.

``0001_initial`` was edited in place after being applied: ``FileExtension``
lost ``dwg``, ``dxf``, ``xls`` and ``xlsx`` and gained ``jpeg`` and ``png``.
Django treats 0001 as applied and never re-runs it, so databases created
before that edit still carry the old CHECK and reject every JPEG or PNG
(``POST /documents`` answered 500). Dropping and recreating the constraint
brings them in line; on a fresh database the operation is a harmless no-op.

The constraint is added ``NOT VALID``: PostgreSQL then enforces it for every
new or updated row but does not scan existing ones, so databases seeded
before the enum change (which hold ``dwg``/``xlsx`` demo files) migrate
without data loss. Django's own ``AddConstraint`` would fail on those rows.

The list is frozen here on purpose, like in every other migration: reading
``FileExtension.values`` at import time would make this file change meaning
whenever the enum changes and hide the need for the next migration.
``core/tests/test_file_model.py`` checks that the database accepts every
value of the enum and rejects the removed ones.
"""

from django.db import migrations, models

STORABLE_EXTENSIONS = ["pdf", "doc", "docx", "jpeg", "png"]

ADD_CONSTRAINT_NOT_VALID = """
    ALTER TABLE "file" ADD CONSTRAINT "ck_file_extension"
        CHECK ("extension" IN ('pdf', 'doc', 'docx', 'jpeg', 'png')) NOT VALID;
"""

DROP_CONSTRAINT = 'ALTER TABLE "file" DROP CONSTRAINT "ck_file_extension";'


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_triggers"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="file", name="ck_file_extension"),
        migrations.RunSQL(
            sql=ADD_CONSTRAINT_NOT_VALID,
            reverse_sql=DROP_CONSTRAINT,
            state_operations=[
                migrations.AddConstraint(
                    model_name="file",
                    constraint=models.CheckConstraint(
                        condition=models.Q(("extension__in", STORABLE_EXTENSIONS)),
                        name="ck_file_extension",
                    ),
                ),
            ],
        ),
    ]
