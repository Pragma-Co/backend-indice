from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_remove_project_disciplines"),
        ("core", "0025_merge_access_groups_and_saved_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="userlegalacceptance",
            name="accepted",
            field=models.BooleanField(default=True),
        ),
        migrations.RemoveConstraint(
            model_name="userlegalacceptance",
            name="uq_user_legal_acceptance_in_force",
        ),
        migrations.AddConstraint(
            model_name="userlegalacceptance",
            constraint=models.UniqueConstraint(
                condition=models.Q(("accepted", True), ("revoked_at__isnull", True)),
                fields=("user", "version"),
                name="uq_user_legal_acceptance_in_force",
            ),
        ),
    ]