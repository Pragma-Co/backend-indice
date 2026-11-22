import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0023_document_access_type_and_expiry"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_by_users",
                        to="core.document",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "saved_document",
                "indexes": [
                    models.Index(
                        fields=["user", "-created_at", "-id"], name="ix_saved_document_recent"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "document"), name="uq_saved_document")
                ],
            },
        ),
    ]
