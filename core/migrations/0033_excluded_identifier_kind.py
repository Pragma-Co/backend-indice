from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_merge_data_incidents_and_document_access_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="excludedidentifier",
            name="kind",
            field=models.CharField(
                choices=[("ANONYMIZED", "Anonymized"), ("DELETED", "Deleted")],
                default="ANONYMIZED",
                max_length=10,
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="excludedidentifier",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["ANONYMIZED", "DELETED"])),
                name="ck_excluded_identifier_kind",
            ),
        ),
    ]
