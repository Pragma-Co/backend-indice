from django.db import migrations, models


def mark_changed_files(apps, schema_editor):
    Document = apps.get_model("core", "Document")
    Revision = apps.get_model("core", "Revision")

    for document in Document.objects.all().iterator():
        previous_hashes = {}
        revisions = Revision.objects.filter(document_id=document.pk).order_by("version")
        for revision in revisions:
            for position, file in enumerate(revision.files.order_by("id")):
                file.revision_changed = previous_hashes.get(position) != file.sha256
                file.save(update_fields=["revision_changed"])
                previous_hashes[position] = file.sha256


class Migration(migrations.Migration):
    dependencies = [("core", "0011_rebuild_file_groups")]

    operations = [
        migrations.AddField(
            model_name="file",
            name="revision_changed",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(mark_changed_files, migrations.RunPython.noop),
    ]
