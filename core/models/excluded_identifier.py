from django.db import models
from django.db.models.functions import Now


class ExcludedIdentifier(models.Model):
    identifier_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "excluded_identifier"

    def __str__(self):
        return f"Excluded identifier {self.pk}"
