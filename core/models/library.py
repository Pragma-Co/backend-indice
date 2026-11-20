from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.document import Document


class SavedDocument(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_documents",
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="saved_by_users",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "saved_document"
        constraints = [
            models.UniqueConstraint(fields=["user", "document"], name="uq_saved_document"),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at", "-id"], name="ix_saved_document_recent"),
        ]

    def __str__(self):
        return f"{self.user_id}@{self.document_id}"
