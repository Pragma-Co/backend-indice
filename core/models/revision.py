"""Revisions and their stored files — the versioned side of a document."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.choices import FileExtension, RevisionStatus
from core.models.document import Document

#: Upload ceiling (100 MB). Engineering drawings are large, so the binary
#: itself stays outside the database — only the path and the hash are stored.
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class Revision(models.Model):
    """One version of a document. Versions are sequential integers from 1."""

    # CASCADE: a revision has no meaning without its document.
    # db_index=False: `uq_revision_document_version` already leads with
    # document_id, so a second index on it would only cost writes.
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="revisions", db_index=False
    )
    version = models.SmallIntegerField(default=1)
    status = models.CharField(
        max_length=10, choices=RevisionStatus.choices, default=RevisionStatus.PENDING
    )
    issue_date = models.DateField(null=True, blank=True)
    change_description = models.CharField(max_length=255, null=True, blank=True)
    # RESTRICT: the author and the auditor of a revision are part of the
    # record and cannot be deleted (users are deactivated instead)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_revisions",
    )
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audited_revisions",
    )
    auditor_comment = models.TextField(null=True, blank=True)
    audited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "revision"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version"], name="uq_revision_document_version"
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="ck_revision_version_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RevisionStatus.values),
                name="ck_revision_status",
            ),
            models.CheckConstraint(
                # A decision only exists together with who took it and when
                condition=models.Q(status=RevisionStatus.PENDING)
                | (
                    models.Q(auditor__isnull=False)
                    & models.Q(audited_at__isnull=False)
                ),
                name="ck_revision_decision_has_auditor",
            ),
            # One current revision per document. Doubles as the read index
            # for "give me the approved revision of this document".
            models.UniqueConstraint(
                fields=["document"],
                condition=models.Q(status=RevisionStatus.APPROVED),
                name="uq_revision_current",
            ),
        ]
        indexes = [
            models.Index(fields=["-issue_date"], name="ix_revision_issue_date"),
            # The manager's approval queue
            models.Index(
                fields=["created_at"],
                condition=models.Q(status=RevisionStatus.PENDING),
                name="ix_revision_pending",
            ),
        ]

    def __str__(self):
        return f"{self.document_id} v{self.version} ({self.status})"


class File(models.Model):
    """A file attached to a revision. Only metadata; the bytes live in storage."""

    # db_index=False: `uq_file_revision_sha256` already leads with revision_id
    revision = models.ForeignKey(
        Revision, on_delete=models.CASCADE, related_name="files", db_index=False
    )
    original_name = models.CharField(max_length=255)
    extension = models.CharField(max_length=5, choices=FileExtension.choices)
    mime_type = models.CharField(max_length=127)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    storage_path = models.CharField(max_length=500, unique=True)
    uploaded_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "file"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(extension__in=FileExtension.values),
                name="ck_file_extension",
            ),
            models.CheckConstraint(
                condition=models.Q(size_bytes__gt=0)
                & models.Q(size_bytes__lte=MAX_FILE_SIZE_BYTES),
                name="ck_file_size_bytes",
            ),
            models.CheckConstraint(
                condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="ck_file_sha256_hex",
            ),
            # The same file cannot be attached twice to one revision
            models.UniqueConstraint(
                fields=["revision", "sha256"], name="uq_file_revision_sha256"
            ),
        ]
        indexes = [
            # Integrity checks and duplicate detection across revisions
            models.Index(fields=["sha256"], name="ix_file_sha256"),
        ]

    def __str__(self):
        return self.original_name
