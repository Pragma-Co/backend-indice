"""Append-only audit trail."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.choices import AuditAction


class AuditLog(models.Model):
    """One row per relevant event, kept even after the target is deleted.

    `entity`/`entity_id` are deliberately plain columns with no foreign key:
    the trail has to survive the deletion of whatever it points at. Migration
    0003 makes the table append-only at the database level.
    """

    occurred_at = models.DateTimeField(db_default=Now(), editable=False)
    # SET_NULL: the event keeps its value after the user is gone
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        # db_index=False: `ix_audit_user` already leads with user_id.
        # This table only ever receives INSERTs, so every extra index is
        # pure write cost — three is the ceiling here.
        db_index=False,
    )
    action = models.CharField(max_length=10, choices=AuditAction.choices)
    entity = models.CharField(max_length=40)
    entity_id = models.BigIntegerField(null=True, blank=True)
    record = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=AuditAction.values),
                name="ck_audit_log_action",
            ),
        ]
        indexes = [
            # "what happened to this record"
            models.Index(
                fields=["entity", "entity_id", "-occurred_at"], name="ix_audit_entity"
            ),
            # "what this person did" — the audit screen per collaborator
            models.Index(fields=["user", "-occurred_at"], name="ix_audit_user"),
        ]

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.action} {self.entity}"
