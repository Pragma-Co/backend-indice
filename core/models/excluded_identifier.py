from django.db import models


class ExcludedIdentifier(models.Model):
    identifier_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "excluded_identifier"

    def __str__(self):
        return f"Excluded identifier {self.pk}"
