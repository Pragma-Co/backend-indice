from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0018_merge_document_archiving_and_legal_documents")]

    operations = [
        migrations.RemoveConstraint(
            model_name="userlegalacceptance",
            name="uq_user_legal_acceptance",
        ),
        migrations.AddConstraint(
            model_name="userlegalacceptance",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True)),
                fields=("user", "version"),
                name="uq_user_legal_acceptance_in_force",
            ),
        ),
    ]
