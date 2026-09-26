# Generated migration for adding updated_by field

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_document_created_by_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="updated_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["updated_by"], name="ix_document_updated_by"),
        ),
    ]
