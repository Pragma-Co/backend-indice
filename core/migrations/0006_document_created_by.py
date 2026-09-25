# Generated migration to add created_by field to Document model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0005_document_listing_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='created_by',
            field=models.ForeignKey(
                default=1,  # This is a temporary default for existing records
                on_delete=django.db.models.deletion.PROTECT,
                related_name='created_documents',
                to=settings.AUTH_USER_MODEL
            ),
            preserve_default=False,
        ),
    ]
