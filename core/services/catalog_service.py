"""Queries behind the catalog endpoints: only active entries, sorted by name."""

from django.db.models import QuerySet

from core.models import Discipline, Project


def list_active_projects() -> QuerySet[Project]:
    return Project.objects.filter(active=True).order_by("name", "id")


def list_active_disciplines() -> QuerySet[Discipline]:
    return Discipline.objects.filter(active=True).order_by("name", "id")
