from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Now

from core.models.choices import (
    IncidentActionKind,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    PersonalDataCategory,
)
from core.models.document import Document


class DataIncident(models.Model):
    reference = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    incident_type = models.CharField(max_length=25, choices=IncidentType.choices)
    severity = models.CharField(max_length=10, choices=IncidentSeverity.choices)
    status = models.CharField(
        max_length=12, choices=IncidentStatus.choices, default=IncidentStatus.REPORTED
    )
    occurred_at = models.DateTimeField()
    detected_at = models.DateTimeField()
    reported_at = models.DateTimeField(db_default=Now(), editable=False)
    affected_data_categories = ArrayField(
        models.CharField(max_length=20, choices=PersonalDataCategory.choices), default=list
    )
    affected_subjects_count = models.PositiveIntegerField(default=0)
    affected_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="core.DataIncidentAffectedUser",
        through_fields=("incident", "user"),
        related_name="incidents_affecting",
    )
    affected_documents = models.ManyToManyField(
        Document, through="core.DataIncidentAffectedDocument", related_name="incidents"
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_incidents"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_incidents",
    )
    root_cause = models.TextField(blank=True)
    authority_notification_required = models.BooleanField(default=False)
    authority_notification_due_at = models.DateTimeField(null=True, blank=True)
    authority_notified_at = models.DateTimeField(null=True, blank=True)
    subjects_notified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "data_incident"
        ordering = ["-reported_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(title__regex=r"\S"), name="ck_data_incident_title_not_blank"
            ),
            models.CheckConstraint(
                condition=models.Q(incident_type__in=IncidentType.values),
                name="ck_data_incident_type",
            ),
            models.CheckConstraint(
                condition=models.Q(severity__in=IncidentSeverity.values),
                name="ck_data_incident_severity",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=IncidentStatus.values),
                name="ck_data_incident_status",
            ),
            models.CheckConstraint(
                condition=models.Q(detected_at__gte=models.F("occurred_at")),
                name="ck_data_incident_detection_after_occurrence",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=IncidentStatus.CLOSED, closed_at__isnull=False)
                    | (~models.Q(status=IncidentStatus.CLOSED) & models.Q(closed_at__isnull=True))
                ),
                name="ck_data_incident_closed_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(authority_notification_required=False)
                    | models.Q(authority_notification_due_at__isnull=False)
                ),
                name="ck_data_incident_authority_deadline",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-reported_at"], name="ix_data_incident_status"),
            models.Index(fields=["severity"], name="ix_data_incident_severity"),
        ]

    def __str__(self):
        return f"{self.reference} — {self.title}"


class DataIncidentAffectedUser(models.Model):
    incident = models.ForeignKey(
        DataIncident, on_delete=models.CASCADE, related_name="affected_user_links", db_index=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="incident_links"
    )

    class Meta:
        db_table = "data_incident_affected_user"
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "user"], name="uq_data_incident_affected_user"
            ),
        ]

    def __str__(self):
        return f"{self.user_id}@{self.incident_id}"


class DataIncidentAffectedDocument(models.Model):
    incident = models.ForeignKey(
        DataIncident,
        on_delete=models.CASCADE,
        related_name="affected_document_links",
        db_index=False,
    )
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="incident_links")

    class Meta:
        db_table = "data_incident_affected_document"
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "document"], name="uq_data_incident_affected_document"
            ),
        ]

    def __str__(self):
        return f"{self.document_id}@{self.incident_id}"


class DataIncidentAction(models.Model):
    incident = models.ForeignKey(
        DataIncident, on_delete=models.CASCADE, related_name="actions", db_index=False
    )
    kind = models.CharField(max_length=15, choices=IncidentActionKind.choices)
    description = models.TextField()
    performed_at = models.DateTimeField()
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="performed_incident_actions",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_incident_actions",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "data_incident_action"
        ordering = ["performed_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=IncidentActionKind.values),
                name="ck_data_incident_action_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(description__regex=r"\S"),
                name="ck_data_incident_action_description_not_blank",
            ),
        ]
        indexes = [
            models.Index(fields=["incident", "performed_at"], name="ix_data_incident_action"),
        ]

    def __str__(self):
        return f"{self.incident_id}: {self.kind} at {self.performed_at:%Y-%m-%d %H:%M}"


class DataIncidentStatusChange(models.Model):
    incident = models.ForeignKey(
        DataIncident, on_delete=models.CASCADE, related_name="status_changes", db_index=False
    )
    from_status = models.CharField(
        max_length=12, choices=IncidentStatus.choices, blank=True, default=""
    )
    to_status = models.CharField(max_length=12, choices=IncidentStatus.choices)
    note = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incident_status_changes"
    )
    changed_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "data_incident_status_change"
        ordering = ["changed_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_status__in=IncidentStatus.values),
                name="ck_data_incident_status_change_to",
            ),
        ]
        indexes = [
            models.Index(fields=["incident", "changed_at"], name="ix_data_incident_status_chg"),
        ]

    def __str__(self):
        return f"{self.incident_id}: {self.from_status} -> {self.to_status}"
