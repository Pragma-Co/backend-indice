# Generated migration to add index on created_by field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_document_created_by'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='document',
            index=models.Index(
                fields=['created_by'],
                name='ix_document_created_by',
            ),
        ),
    ]
