from django.db import migrations, models

FILL_NULL_TEXT_FIELDS = """
    UPDATE "document" SET "description" = '' WHERE "description" IS NULL;
    UPDATE "document_access" SET "justification" = '' WHERE "justification" IS NULL;
    UPDATE "revision" SET "auditor_comment" = '' WHERE "auditor_comment" IS NULL;
    UPDATE "revision" SET "change_description" = '' WHERE "change_description" IS NULL;
"""

AUDIT_ACTION_CHOICES = [
    ("CREATE", "Create"),
    ("READ", "Read"),
    ("UPDATE", "Update"),
    ("DELETE", "Delete"),
    ("LOGIN", "Login"),
    ("DOC_UPLOAD_SUCCESS", "Document upload succeeded"),
    ("DOC_UPLOAD_DUPLICATE", "Duplicate document upload attempted"),
    ("DOC_SUBMIT_SUCCESS", "Document registration submitted"),
    ("DOC_CANCEL", "Document registration cancelled"),
    ("DOC_DOWNLOAD", "Document downloaded"),
    ("DOC_ACCESS_REQUESTED", "Document access requested"),
]
AUDIT_ACTIONS = [value for value, _label in AUDIT_ACTION_CHOICES]


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
        migrations.RemoveConstraint(model_name="auditlog", name="ck_audit_log_action"),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(choices=AUDIT_ACTION_CHOICES, max_length=30),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["-occurred_at"], name="ix_audit_occurred_at"),
        ),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(("action__in", AUDIT_ACTIONS)),
                name="ck_audit_log_action",
            ),
        ),
    ]
