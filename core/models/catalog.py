"""Controlled vocabularies: projects, disciplines, document types and tags.

These are small, mostly-static tables maintained by the area manager. Rows are
deactivated (`active = false`) instead of deleted, so an existing document
never loses the catalog entry it points at.
"""

from django.db import models
from django.db.models.functions import Lower, Now

from core.models.functions import ImmutableUnaccent


class Project(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    disciplines = models.ManyToManyField(
        "core.Discipline",
        through="core.ProjectDiscipline",
        related_name="projects",
    )

    class Meta:
        db_table = "project"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Discipline(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "discipline"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class DocumentType(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "document_type"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class ProjectDiscipline(models.Model):
    """Disciplines a project is broken down into. Composite primary key."""

    pk = models.CompositePrimaryKey("project_id", "discipline_id")
    # db_index=False: the composite primary key already leads with project_id
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="project_disciplines",
        db_index=False,
    )
    # RESTRICT: a discipline in use by a project cannot be deleted
    discipline = models.ForeignKey(
        Discipline, on_delete=models.PROTECT, related_name="project_disciplines"
    )

    class Meta:
        db_table = "project_discipline"

    def __str__(self):
        return f"{self.project_id}/{self.discipline_id}"


class Tag(models.Model):
    """Free-form keyword. Any author may create one."""

    name = models.CharField(max_length=60, unique=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "tag"
        ordering = ["name"]
        constraints = [
            # `unique` above already blocks an exact repeat; this one also
            # blocks the same tag written with a different case or accent,
            # so "P&ID", "p&id" and "P&ÍD" cannot coexist.
            models.UniqueConstraint(
                Lower(ImmutableUnaccent("name")),
                name="uq_tag_name_norm",
            ),
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="ck_tag_name_not_blank",
            ),
        ]

    def __str__(self):
        return self.name
