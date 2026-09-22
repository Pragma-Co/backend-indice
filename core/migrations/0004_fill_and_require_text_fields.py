from django.db import migrations, models

FILL_NULL_TEXT_FIELDS = """
    UPDATE "document" SET "description" = '' WHERE "description" IS NULL;
    UPDATE "document_access" SET "justification" = '' WHERE "justification" IS NULL;
    UPDATE "revision" SET "auditor_comment" = '' WHERE "auditor_comment" IS NULL;
    UPDATE "revision" SET "change_description" = '' WHERE "change_description" IS NULL;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_align_file_extension_constraint"),
    ]

    operations = [
        migrations.RunSQL(sql=FILL_NULL_TEXT_FIELDS, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="document",
            name="description",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="documentaccess",
            name="justification",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="revision",
            name="auditor_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="revision",
            name="change_description",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
