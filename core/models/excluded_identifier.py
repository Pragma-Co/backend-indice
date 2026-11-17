from django.db import models
from django.db.models.functions import Now

from core.models.choices import ErasureKind


class ExcludedIdentifier(models.Model):
    identifier_hash = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=10, choices=ErasureKind.choices)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "excluded_identifier"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=ErasureKind.values),
                name="ck_excluded_identifier_kind",
            )
        ]

    def __str__(self):
        return f"Excluded identifier {self.pk}"
