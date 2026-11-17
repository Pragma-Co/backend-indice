from django.db import migrations, models

NOTIFICATION_TYPES = [
    ('DOCUMENT_UPDATED', 'Document updated'),
    ('ACCESS_APPROVED', 'Access approved'),
    ('ACCESS_REJECTED', 'Access rejected'),
    ('REVISION_APPROVED', 'Revision approved'),
    ('REVISION_REJECTED', 'Revision rejected'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_document_access_group'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='notification',
            name='ck_notification_type',
        ),
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(choices=NOTIFICATION_TYPES, max_length=20),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.CheckConstraint(
                condition=models.Q(('type__in', [value for value, _ in NOTIFICATION_TYPES])),
                name='ck_notification_type',
            ),
        ),
    ]
