"""The document itself, plus its area and tag classifications."""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Now

from core.models.catalog import Discipline, DocumentType, Project
from core.models.choices import ConfidentialityLevel
from core.models.organization import Area


class Document(models.Model):
    """A controlled document. Its content lives in revisions, never here."""

    code = models.CharField(max_length=60, unique=True)
    title = models.CharField(max_length=255)
    description = models.CharField(max_length=500, null=True, blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="documents"
    )
    discipline = models.ForeignKey(
        Discipline, on_delete=models.PROTECT, related_name="documents"
    )
    confidentiality_level = models.CharField(
        max_length=12,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.CONFIDENTIAL,
    )
    document_type = models.ForeignKey(
        DocumentType, on_delete=models.PROTECT, related_name="documents"
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_documents",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    updated_at = models.DateTimeField(db_default=Now(), editable=False)

    areas = models.ManyToManyField(
        Area, through="core.DocumentArea", related_name="documents"
    )
    tags = models.ManyToManyField(
        "core.Tag", through="core.DocumentTag", related_name="documents"
    )

    class Meta:
        db_table = "document"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(title__regex=r"\S"),
                name="ck_document_title_not_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    confidentiality_level__in=ConfidentialityLevel.values
                ),
                name="ck_document_confidentiality_level",
            ),
        ]
        indexes = [
            GinIndex(
                fields=["title"],
                opclasses=["gin_trgm_ops"],
                name="ix_document_title_trgm",
            ),
            models.Index(
                fields=[
                    "project",
                    "discipline",
                    "document_type",
                    "confidentiality_level",
                ],
                name="ix_document_filters",
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.title}"


class DocumentArea(models.Model):
    """Areas a document is classified under. Composite primary key.

    At least one area per document is a rule the database cannot express; the
    application creates the document and its areas in the same transaction.
    """

    pk = models.CompositePrimaryKey("document_id", "area_id")
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="document_areas",
        db_index=False,
    )
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, related_name="document_areas"
    )

    class Meta:
        db_table = "document_area"

    def __str__(self):
        return f"{self.document_id}/{self.area_id}"


class DocumentTag(models.Model):
    """Keywords attached to a document. Composite primary key."""

    pk = models.CompositePrimaryKey("document_id", "tag_id")
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="document_tags",
        db_index=False,
    )
    tag = models.ForeignKey(
        "core.Tag", on_delete=models.CASCADE, related_name="document_tags"
    )

    class Meta:
        db_table = "document_tag"

    def __str__(self):
        return f"{self.document_id}/{self.tag_id}"
