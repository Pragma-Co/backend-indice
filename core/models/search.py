from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from core.models.document import Document
from core.models.revision import Revision

SEARCH_CONFIG = "portuguese_unaccent"
THEMATIC_TAG_MAX_LENGTH = 60


class DocumentContent(models.Model):
    document = models.OneToOneField(
        Document, on_delete=models.CASCADE, primary_key=True, related_name="indexed_content"
    )
    revision = models.ForeignKey(
        Revision, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    content = models.TextField(blank=True)
    thematic_tags = ArrayField(
        models.CharField(max_length=THEMATIC_TAG_MAX_LENGTH), default=list, blank=True
    )
    search_vector = SearchVectorField(null=True, editable=False)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "document_content"
        indexes = [
            GinIndex(fields=["search_vector"], name="ix_document_content_search"),
        ]

    def __str__(self):
        return f"{self.document_id} ({len(self.thematic_tags)} tags)"
