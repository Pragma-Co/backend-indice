import uuid

from django.db import migrations


def rebuild_file_groups(apps, schema_editor):
    Document = apps.get_model("core", "Document")
    Revision = apps.get_model("core", "Revision")

    for document in Document.objects.all().iterator():
        groups = {}
        revisions = Revision.objects.filter(document_id=document.pk).order_by("version")
        for revision in revisions:
            files = revision.files.order_by("id")
            for position, file in enumerate(files):
                group = groups.setdefault(position, uuid.uuid4())
                file.file_group = group
                file.save(update_fields=["file_group"])


class Migration(migrations.Migration):
    dependencies = [("core", "0010_file_group")]

    operations = [migrations.RunPython(rebuild_file_groups, migrations.RunPython.noop)]
