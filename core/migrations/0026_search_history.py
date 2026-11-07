import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_merge_access_groups_and_saved_document"),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("term", models.CharField(max_length=200)),
                ("normalized_term", models.CharField(max_length=600)),
                ("searched_at", models.DateTimeField()),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="search_history", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "search_history",
                "indexes": [models.Index(fields=["user", "-searched_at", "-id"], name="ix_user_search_recent")],
                "constraints": [models.UniqueConstraint(fields=("user", "normalized_term"), name="uq_user_search_term")],
            },
        ),
    ]