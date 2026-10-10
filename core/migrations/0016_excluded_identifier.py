from django.db import migrations, models
from django.db.models.functions import Now


class Migration(migrations.Migration):
    dependencies = [("core", "0015_user_deletion_requested_at")]

    operations = [
        migrations.CreateModel(
            name="ExcludedIdentifier",
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
                ("identifier_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(db_default=Now(), editable=False)),
            ],
            options={"db_table": "excluded_identifier"},
        ),
    ]
