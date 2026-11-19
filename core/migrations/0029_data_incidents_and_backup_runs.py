import django.contrib.postgres.fields
import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models


CREATE_STATUS_HISTORY_APPEND_ONLY = """
    CREATE OR REPLACE FUNCTION data_incident_status_change_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'data_incident_status_change is append-only (% is not allowed)', TG_OP;
    END;
    $$;

    CREATE TRIGGER data_incident_status_change_no_update_delete
        BEFORE UPDATE OR DELETE ON data_incident_status_change
        FOR EACH ROW EXECUTE FUNCTION data_incident_status_change_append_only();
"""

DROP_STATUS_HISTORY_APPEND_ONLY = """
    DROP TRIGGER IF EXISTS data_incident_status_change_no_update_delete
        ON data_incident_status_change;
    DROP FUNCTION IF EXISTS data_incident_status_change_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0028_capture_attempt_audit_action"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataIncident",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reference", models.CharField(max_length=20, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField()),
                (
                    "incident_type",
                    models.CharField(
                        choices=[
                            ("UNAUTHORIZED_ACCESS", "Unauthorized access"),
                            ("IMPROPER_DISCLOSURE", "Improper disclosure"),
                            ("DATA_LOSS", "Loss or destruction of data"),
                            ("CREDENTIAL_EXPOSURE", "Credential exposure"),
                            ("MISDIRECTED_DELIVERY", "Data sent to the wrong recipient"),
                            ("MALICIOUS_SOFTWARE", "Malicious software"),
                            ("OTHER", "Other"),
                        ],
                        max_length=25,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("LOW", "Low"),
                            ("MEDIUM", "Medium"),
                            ("HIGH", "High"),
                            ("CRITICAL", "Critical"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("REPORTED", "Reported"),
                            ("CONTAINMENT", "Under containment"),
                            ("ANALYSIS", "Under analysis"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        default="REPORTED",
                        max_length=12,
                    ),
                ),
                ("occurred_at", models.DateTimeField()),
                ("detected_at", models.DateTimeField()),
                (
                    "reported_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "affected_data_categories",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(
                            choices=[
                                ("IDENTIFICATION", "Identification (name, email)"),
                                ("CREDENTIALS", "Credentials"),
                                ("PROFESSIONAL", "Professional data (role, area)"),
                                ("ACCESS_HISTORY", "Access and audit history"),
                                ("DOCUMENT_CONTENT", "Content of technical documents"),
                                ("OTHER", "Other"),
                            ],
                            max_length=20,
                        ),
                        default=list,
                        size=None,
                    ),
                ),
                ("affected_subjects_count", models.PositiveIntegerField(default=0)),
                ("root_cause", models.TextField(blank=True)),
                ("authority_notification_required", models.BooleanField(default=False)),
                ("authority_notification_due_at", models.DateTimeField(blank=True, null=True)),
                ("authority_notified_at", models.DateTimeField(blank=True, null=True)),
                ("subjects_notified_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assigned_incidents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reported_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reported_incidents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "data_incident",
                "ordering": ["-reported_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DataIncidentAffectedDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incident_links",
                        to="core.document",
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affected_document_links",
                        to="core.dataincident",
                    ),
                ),
            ],
            options={
                "db_table": "data_incident_affected_document",
            },
        ),
        migrations.AddField(
            model_name="dataincident",
            name="affected_documents",
            field=models.ManyToManyField(
                related_name="incidents",
                through="core.DataIncidentAffectedDocument",
                to="core.document",
            ),
        ),
        migrations.CreateModel(
            name="DataIncidentAffectedUser",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affected_user_links",
                        to="core.dataincident",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incident_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "data_incident_affected_user",
            },
        ),
        migrations.AddField(
            model_name="dataincident",
            name="affected_users",
            field=models.ManyToManyField(
                related_name="incidents_affecting",
                through="core.DataIncidentAffectedUser",
                through_fields=("incident", "user"),
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="DataIncidentStatusChange",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("REPORTED", "Reported"),
                            ("CONTAINMENT", "Under containment"),
                            ("ANALYSIS", "Under analysis"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        default="",
                        max_length=12,
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("REPORTED", "Reported"),
                            ("CONTAINMENT", "Under containment"),
                            ("ANALYSIS", "Under analysis"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        max_length=12,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                (
                    "changed_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incident_status_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_changes",
                        to="core.dataincident",
                    ),
                ),
            ],
            options={
                "db_table": "data_incident_status_change",
                "ordering": ["changed_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="BackupRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "target",
                    models.CharField(
                        choices=[("POSTGRES", "PostgreSQL"), ("MONGODB", "MongoDB")], max_length=10
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("RUNNING", "Running"),
                            ("SUCCEEDED", "Succeeded"),
                            ("FAILED", "Failed"),
                        ],
                        default="RUNNING",
                        max_length=10,
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("destination", models.CharField(blank=True, max_length=500)),
                ("size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("encrypted", models.BooleanField(default=False)),
                ("record_count", models.IntegerField(blank=True, null=True)),
                ("error", models.CharField(blank=True, max_length=120)),
                ("pruned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "triggered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="triggered_backups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "backup_run",
                "ordering": ["-started_at", "-id"],
                "indexes": [
                    models.Index(fields=["target", "-started_at"], name="ix_backup_run_target")
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("target__in", ["POSTGRES", "MONGODB"])),
                        name="ck_backup_run_target",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["RUNNING", "SUCCEEDED", "FAILED"])),
                        name="ck_backup_run_status",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DataIncidentAction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("CONTAINMENT", "Containment"),
                            ("ERADICATION", "Eradication"),
                            ("RECOVERY", "Recovery"),
                            ("COMMUNICATION", "Communication"),
                            ("OTHER", "Other"),
                        ],
                        max_length=15,
                    ),
                ),
                ("description", models.TextField()),
                ("performed_at", models.DateTimeField()),
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
                        related_name="actions",
                        to="core.dataincident",
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="performed_incident_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recorded_incident_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "data_incident_action",
                "ordering": ["performed_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["incident", "performed_at"], name="ix_data_incident_action"
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "kind__in",
                                [
                                    "CONTAINMENT",
                                    "ERADICATION",
                                    "RECOVERY",
                                    "COMMUNICATION",
                                    "OTHER",
                                ],
                            )
                        ),
                        name="ck_data_incident_action_kind",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("description__regex", "\\S")),
                        name="ck_data_incident_action_description_not_blank",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="dataincidentaffecteddocument",
            constraint=models.UniqueConstraint(
                fields=("incident", "document"), name="uq_data_incident_affected_document"
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincidentaffecteduser",
            constraint=models.UniqueConstraint(
                fields=("incident", "user"), name="uq_data_incident_affected_user"
            ),
        ),
        migrations.AddIndex(
            model_name="dataincident",
            index=models.Index(fields=["status", "-reported_at"], name="ix_data_incident_status"),
        ),
        migrations.AddIndex(
            model_name="dataincident",
            index=models.Index(fields=["severity"], name="ix_data_incident_severity"),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(("title__regex", "\\S")), name="ck_data_incident_title_not_blank"
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "incident_type__in",
                        [
                            "UNAUTHORIZED_ACCESS",
                            "IMPROPER_DISCLOSURE",
                            "DATA_LOSS",
                            "CREDENTIAL_EXPOSURE",
                            "MISDIRECTED_DELIVERY",
                            "MALICIOUS_SOFTWARE",
                            "OTHER",
                        ],
                    )
                ),
                name="ck_data_incident_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(("severity__in", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])),
                name="ck_data_incident_severity",
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["REPORTED", "CONTAINMENT", "ANALYSIS", "RESOLVED", "CLOSED"])
                ),
                name="ck_data_incident_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(("detected_at__gte", models.F("occurred_at"))),
                name="ck_data_incident_detection_after_occurrence",
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("closed_at__isnull", False), ("status", "CLOSED")),
                    models.Q(
                        models.Q(("status", "CLOSED"), _negated=True), ("closed_at__isnull", True)
                    ),
                    _connector="OR",
                ),
                name="ck_data_incident_closed_consistency",
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincident",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("authority_notification_required", False),
                    ("authority_notification_due_at__isnull", False),
                    _connector="OR",
                ),
                name="ck_data_incident_authority_deadline",
            ),
        ),
        migrations.AddIndex(
            model_name="dataincidentstatuschange",
            index=models.Index(
                fields=["incident", "changed_at"], name="ix_data_incident_status_chg"
            ),
        ),
        migrations.AddConstraint(
            model_name="dataincidentstatuschange",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("to_status__in", ["REPORTED", "CONTAINMENT", "ANALYSIS", "RESOLVED", "CLOSED"])
                ),
                name="ck_data_incident_status_change_to",
            ),
        ),
        migrations.RunSQL(CREATE_STATUS_HISTORY_APPEND_ONLY, DROP_STATUS_HISTORY_APPEND_ONLY),
    ]
