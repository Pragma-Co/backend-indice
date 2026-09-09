from django.db import models


class Project(models.Model):
    """Project a document belongs to; its code is the first part of the document code."""

    code = models.CharField("code", max_length=20, unique=True)
    name = models.CharField("name", max_length=150)
    active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField("created at", auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "project"
        verbose_name_plural = "projects"

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
