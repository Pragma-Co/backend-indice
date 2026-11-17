import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_merge_data_incidents_and_document_access_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataIncidentSubjectNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("SENT", "Sent"), ("FAILED", "Failed")],
                        default="PENDING",
                        max_length=10,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=100)),
                (
                    "created_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subject_notifications",
                        to="core.dataincident",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incident_subject_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "data_incident_subject_notification",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("incident", "user"), name="uq_data_incident_subject_notification"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["PENDING", "SENT", "FAILED"])),
                        name="ck_data_incident_subject_notification_status",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("sent_at__isnull", False), ("status", "SENT")),
                            models.Q(
                                models.Q(("status", "SENT"), _negated=True),
                                ("sent_at__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="ck_data_incident_subject_notification_sent",
                    ),
                ],
            },
        ),
    ]
