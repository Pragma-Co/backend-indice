from django.db import migrations, models
import django.db.models.deletion


def backfill_created_by(apps, schema_editor):
    Document = apps.get_model("core", "Document")
    alias = schema_editor.connection.alias
    Document.objects.using(alias).filter(created_by__isnull=True).update(
        created_by_id=models.F("responsible_id")
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0013_reconcile_file_revision_history")]

    operations = [
        migrations.RunPython(backfill_created_by, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="document",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_documents",
                to="core.user",
            ),
        ),
    ]
