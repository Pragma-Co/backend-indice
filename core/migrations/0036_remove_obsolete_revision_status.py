from django.db import migrations, models


def obsolete_to_approved(apps, schema_editor):
    Revision = apps.get_model("core", "Revision")
    Revision.objects.filter(status="OBSOLETE").update(status="APPROVED")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0035_merge_subject_notification_and_revision_decision_notifications"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="revision", name="uq_revision_current"),
        migrations.RemoveConstraint(model_name="revision", name="ck_revision_status"),
        migrations.RunPython(obsolete_to_approved, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="revision",
            name="status",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")],
                default="PENDING",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="revision",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["PENDING", "APPROVED", "REJECTED"])),
                name="ck_revision_status",
            ),
        ),
    ]
