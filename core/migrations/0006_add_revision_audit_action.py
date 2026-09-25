from django.db import migrations, models


AUDIT_ACTION_CHOICES = [
    ("CREATE", "Create"),
    ("READ", "Read"),
    ("UPDATE", "Update"),
    ("DELETE", "Delete"),
    ("LOGIN", "Login"),
    ("DOC_UPLOAD_SUCCESS", "Document upload succeeded"),
    ("DOC_UPLOAD_DUPLICATE", "Duplicate document upload attempted"),
    ("DOC_SUBMIT_SUCCESS", "Document registration submitted"),
    ("DOC_REVISION_CREATED", "Document revision created"),
    ("DOC_CANCEL", "Document registration cancelled"),
    ("DOC_DOWNLOAD", "Document downloaded"),
    ("DOC_ACCESS_REQUESTED", "Document access requested"),
]
AUDIT_ACTIONS = [value for value, _label in AUDIT_ACTION_CHOICES]


class Migration(migrations.Migration):
    dependencies = [("core", "0005_document_listing_indexes")]

    operations = [
        migrations.RemoveConstraint(model_name="auditlog", name="ck_audit_log_action"),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(choices=AUDIT_ACTION_CHOICES, max_length=30),
        ),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=models.Q(action__in=AUDIT_ACTIONS),
                name="ck_audit_log_action",
            ),
        ),
    ]
