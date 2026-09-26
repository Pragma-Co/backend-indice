# Generated migration for adding created_by field

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_document_listing_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_documents",
                to=settings.AUTH_USER_MODEL,
                null=True,
            ),
            preserve_default=False,
        ),
    ]
