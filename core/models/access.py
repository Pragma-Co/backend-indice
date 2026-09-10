"""Per-user access grants to a single document."""

from django.conf import settings
from django.db import models

from core.models.choices import AccessStatus
from core.models.document import Document


class DocumentAccess(models.Model):
    """One row per (document, user) pair.

    Covers both flows: a request made by the user (`requested_at` filled, born
    PENDING) and a direct grant by the manager (`requested_at` empty, born
    APPROVED). Revoking is a DELETE of the row, and a new request means
    deleting the old row first — the UNIQUE constraint forces that.
    """

    # db_index=False: `uq_document_access` already leads with document_id
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="accesses", db_index=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_accesses",
    )
    status = models.CharField(
        max_length=10, choices=AccessStatus.choices, default=AccessStatus.PENDING
    )
    justification = models.TextField(null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_accesses",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document_access"
        verbose_name_plural = "document accesses"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "user"], name="uq_document_access"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=AccessStatus.values),
                name="ck_document_access_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=AccessStatus.PENDING)
                    & models.Q(approver__isnull=True)
                )
                | (
                    ~models.Q(status=AccessStatus.PENDING)
                    & models.Q(approver__isnull=False)
                    & models.Q(decided_at__isnull=False)
                ),
                name="ck_document_access_decision",
            ),
        ]
        indexes = [
            # The pending-requests queue of a document
            models.Index(
                fields=["document"],
                condition=models.Q(status=AccessStatus.PENDING),
                name="ix_document_access_pending",
            ),
        ]

    def __str__(self):
        return f"{self.user_id}@{self.document_id} ({self.status})"
