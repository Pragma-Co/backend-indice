from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0029_merge_access_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentaccess",
            name="decision_opinion",
            field=models.TextField(blank=True),
        ),
    ]
