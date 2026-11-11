import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0029_merge_capture_attempt_audit_action_and_notification"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentAccessGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "granted_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="group_grants",
                        to="core.document",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="granted_document_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_grants",
                        to="core.accessgroup",
                    ),
                ),
            ],
            options={
                "db_table": "document_access_group",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("document", "group"), name="uq_document_access_group"
                    )
                ],
            },
        ),
    ]
