from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from core.services.acronym_service import ACRONYM_PATTERN, generate_acronym, is_valid_acronym

ACRONYM_MESSAGE = "The acronym must be exactly three upper-case letters without accents (e.g. TUB)."


class Discipline(models.Model):
    """Discipline (subgroup) of a document; its acronym is the second part of the document code."""

    acronym = models.CharField(
        "acronym",
        max_length=3,
        unique=True,
        blank=True,
        validators=[RegexValidator(ACRONYM_PATTERN, ACRONYM_MESSAGE)],
        help_text="Generated automatically from the first three letters of the name.",
    )
    name = models.CharField("name", max_length=100)
    active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "discipline"
        verbose_name_plural = "disciplines"

    def __str__(self) -> str:
        return f"{self.acronym} - {self.name}"

    def fill_acronym(self) -> None:
        """Derive the acronym from the name when none was given."""
        if not self.acronym:
            self.acronym = generate_acronym(self.name)

    def clean(self) -> None:
        self.fill_acronym()
        if not is_valid_acronym(self.acronym):
            raise ValidationError({"acronym": ACRONYM_MESSAGE})

    def save(self, *args, **kwargs) -> None:
        self.fill_acronym()
        if not is_valid_acronym(self.acronym):
            raise ValidationError({"acronym": ACRONYM_MESSAGE})
        super().save(*args, **kwargs)
