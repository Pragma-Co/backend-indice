from django.db import migrations, models

STORABLE_EXTENSIONS = ["pdf", "docx", "jpeg", "png"]

ADD_CONSTRAINT_NOT_VALID = """
    ALTER TABLE "file" ADD CONSTRAINT "ck_file_extension"
        CHECK ("extension" IN ('pdf', 'docx', 'jpeg', 'png')) NOT VALID;
"""

DROP_CONSTRAINT = 'ALTER TABLE "file" DROP CONSTRAINT "ck_file_extension";'


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_triggers"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="file", name="ck_file_extension"),
        migrations.RunSQL(
            sql=ADD_CONSTRAINT_NOT_VALID,
            reverse_sql=DROP_CONSTRAINT,
            state_operations=[
                migrations.AddConstraint(
                    model_name="file",
                    constraint=models.CheckConstraint(
                        condition=models.Q(("extension__in", STORABLE_EXTENSIONS)),
                        name="ck_file_extension",
                    ),
                ),
            ],
        ),
    ]
