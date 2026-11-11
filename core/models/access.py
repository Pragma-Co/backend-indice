"""Per-user access grants to a single document."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.choices import AccessStatus, AccessType
from core.models.document import Document


class DocumentAccess(models.Model):
    """One row per (document, user) pair.

    Covers both flows: a request made by the user (`requested_at` filled, born
    PENDING) and a direct grant by the manager (`requested_at` empty, born
    APPROVED). Revoking is a DELETE of the row. The UNIQUE constraint keeps a
    single row per pair, so a new request after a rejection or an expired grant
    reopens that row, which keeps its audit entries linked to the document.
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
    justification = models.TextField(blank=True)
    access_type = models.CharField(
        max_length=10, choices=AccessType.choices, default=AccessType.PERMANENT
    )
    expires_on = models.DateField(null=True, blank=True)
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
            models.UniqueConstraint(fields=["document", "user"], name="uq_document_access"),
            models.CheckConstraint(
                condition=models.Q(status__in=AccessStatus.values),
                name="ck_document_access_status",
            ),
            models.CheckConstraint(
                condition=(models.Q(status=AccessStatus.PENDING) & models.Q(approver__isnull=True))
                | (
                    ~models.Q(status=AccessStatus.PENDING)
                    & models.Q(approver__isnull=False)
                    & models.Q(decided_at__isnull=False)
                ),
                name="ck_document_access_decision",
            ),
            models.CheckConstraint(
                condition=models.Q(access_type__in=AccessType.values),
                name="ck_document_access_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(access_type=AccessType.TEMPORARY) & models.Q(expires_on__isnull=False)
                )
                | (models.Q(access_type=AccessType.PERMANENT) & models.Q(expires_on__isnull=True)),
                name="ck_document_access_expiry",
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


class DocumentAccessGroup(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="group_grants", db_index=False
    )
    group = models.ForeignKey(
        "core.AccessGroup", on_delete=models.CASCADE, related_name="document_grants"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="granted_document_groups",
    )
    granted_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "document_access_group"
        constraints = [
            models.UniqueConstraint(fields=["document", "group"], name="uq_document_access_group"),
        ]

    def __str__(self):
        return f"{self.group_id}@{self.document_id}"
