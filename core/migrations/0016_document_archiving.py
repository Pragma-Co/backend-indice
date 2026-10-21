import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0015_user_deletion_requested_at")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="archived_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="archived_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("archived_at__isnull", True), ("archived_by__isnull", True)),
                    models.Q(("archived_at__isnull", False), ("archived_by__isnull", False)),
                    _connector="OR",
                ),
                name="ck_document_archived_consistency",
            ),
        ),
    ]
