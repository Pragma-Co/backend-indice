import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_add_revision_audit_action")]

    operations = [
        migrations.AddField(
            model_name="file",
            name="file_group",
            field=models.UUIDField(default=uuid.uuid4, db_index=True, editable=False),
        ),
    ]
