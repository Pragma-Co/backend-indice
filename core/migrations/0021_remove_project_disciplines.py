from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_merge_document_content_and_legal_acceptance_in_force"),
    ]

    operations = [
        migrations.RemoveField(model_name="project", name="disciplines"),
        migrations.DeleteModel(name="ProjectDiscipline"),
    ]
