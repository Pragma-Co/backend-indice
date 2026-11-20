from django.conf import settings
from django.db import models


class SearchHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_history",
    )
    term = models.CharField(max_length=200)
    normalized_term = models.CharField(max_length=600)
    searched_at = models.DateTimeField()

    class Meta:
        db_table = "search_history"
        constraints = [
            models.UniqueConstraint(fields=["user", "normalized_term"], name="uq_user_search_term"),
        ]
        indexes = [
            models.Index(fields=["user", "-searched_at", "-id"], name="ix_user_search_recent"),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.term}"
