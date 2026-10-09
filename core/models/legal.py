"""Versioned legal texts (terms of use, privacy) and per-user consent (LGPD)."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class LegalDocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"
    RETIRED = "RETIRED", "Retired"


class LegalDocument(models.Model):
    """A kind of legal text, e.g. `data-processing-term`. Content lives in versions."""

    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "legal_document"

    def __str__(self):
        return self.title


class LegalDocumentVersion(models.Model):
    """One immutable-once-published edition of a legal document.

    Old versions are never deleted: they prove what each user agreed to. The
    current version is the PUBLISHED one with the highest `version`; a user whose
    latest acceptance points to an older version must be offered the new one.
    """

    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10, choices=LegalDocumentStatus.choices, default=LegalDocumentStatus.DRAFT
    )
    # Preamble/parties/closing text that does not belong to any clause
    summary = models.TextField(blank=True)
    change_notes = models.TextField(blank=True)
    # SHA-256 of the full rendered text, filled at publication
    content_hash = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_legal_versions",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "legal_document_version"
        constraints = [
            models.UniqueConstraint(fields=["document", "version"], name="uq_legal_version"),
            models.CheckConstraint(
                condition=models.Q(status__in=LegalDocumentStatus.values),
                name="ck_legal_version_status",
            ),
            models.CheckConstraint(
                condition=models.Q(status=LegalDocumentStatus.DRAFT)
                | models.Q(published_at__isnull=False),
                name="ck_legal_version_published_at",
            ),
        ]
        indexes = [
            models.Index(
                fields=["document", "-version"],
                condition=models.Q(status=LegalDocumentStatus.PUBLISHED),
                name="ix_legal_version_published",
            ),
        ]

    def __str__(self):
        return f"{self.document_id} v{self.version} ({self.status})"


class LegalClause(models.Model):
    """A clause (article) of a version. Required ones must be accepted to use the system."""

    version = models.ForeignKey(
        LegalDocumentVersion, on_delete=models.PROTECT, related_name="clauses", db_index=False
    )
    # Stable identifier across versions (e.g. "international-transfer"), so the
    # same clause can be tracked as it evolves
    code = models.SlugField(max_length=60)
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_required = models.BooleanField(default=True)

    class Meta:
        db_table = "legal_clause"
        constraints = [
            # Both uniques lead with version_id, so no extra FK index is needed
            models.UniqueConstraint(fields=["version", "code"], name="uq_legal_clause_code"),
            models.UniqueConstraint(
                fields=["version", "position"], name="uq_legal_clause_position"
            ),
            models.CheckConstraint(
                condition=models.Q(body__regex=r"\S"), name="ck_legal_clause_body_not_blank"
            ),
        ]

    def __str__(self):
        return f"{self.version_id}/{self.code}"


class UserLegalAcceptance(models.Model):
    """A user's signature of one version: the proof of consent.

    Append-only evidence. Revoking sets `revoked_at` instead of deleting.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="legal_acceptances",
    )
    version = models.ForeignKey(
        LegalDocumentVersion, on_delete=models.PROTECT, related_name="acceptances"
    )
    accepted_at = models.DateTimeField(db_default=Now(), editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "user_legal_acceptance"
        constraints = [
            models.UniqueConstraint(fields=["user", "version"], name="uq_user_legal_acceptance"),
            models.CheckConstraint(
                condition=models.Q(revoked_at__isnull=True)
                | models.Q(revoked_at__gte=models.F("accepted_at")),
                name="ck_user_legal_acceptance_revoked",
            ),
        ]
        indexes = [models.Index(fields=["version"], name="ix_legal_acceptance_version")]

    def __str__(self):
        return f"{self.user_id}@{self.version_id}"


class UserClauseConsent(models.Model):
    """The user's answer (agreed or not) to each clause of the signed version.

    One row per clause of the version, so "declined" is explicit rather than
    inferred from a missing row. The rule "required clauses must be accepted" spans
    tables, so the application enforces it when creating the acceptance.
    """

    pk = models.CompositePrimaryKey("acceptance_id", "clause_id")
    acceptance = models.ForeignKey(
        UserLegalAcceptance,
        on_delete=models.CASCADE,
        related_name="clause_consents",
        db_index=False,
    )
    clause = models.ForeignKey(
        LegalClause, on_delete=models.PROTECT, related_name="clause_consents"
    )
    accepted = models.BooleanField()
    decided_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "user_clause_consent"

    def __str__(self):
        return f"{self.acceptance_id}/{self.clause_id}={self.accepted}"
