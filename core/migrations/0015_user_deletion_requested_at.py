from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0014_require_document_created_by")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="deletion_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
