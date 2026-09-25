import uuid

from django.db import migrations


def reconcile_file_history(apps, schema_editor):
    Document = apps.get_model("core", "Document")
    Revision = apps.get_model("core", "Revision")

    for document in Document.objects.all().iterator():
        known_groups = {}
        previous_groups = set()
        revisions = Revision.objects.filter(document_id=document.pk).order_by("version")
        for revision in revisions:
            files = list(revision.files.order_by("id"))
            matched_groups = set()
            unmatched_groups = previous_groups - {
                known_groups[file.sha256] for file in files if file.sha256 in known_groups
            }
            for file in files:
                group = known_groups.get(file.sha256)
                if group is None:
                    group = unmatched_groups.pop() if unmatched_groups else uuid.uuid4()
                    changed = True
                    known_groups[file.sha256] = group
                else:
                    changed = False
                file.file_group = group
                file.revision_changed = changed
                file.save(update_fields=["file_group", "revision_changed"])
                matched_groups.add(group)
            previous_groups = matched_groups


class Migration(migrations.Migration):
    dependencies = [("core", "0009_mark_changed_revision_files")]

    operations = [migrations.RunPython(reconcile_file_history, migrations.RunPython.noop)]
