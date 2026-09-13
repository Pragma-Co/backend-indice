"""Queries behind the catalog endpoints: only active entries, sorted by name.

The catalogs themselves (`Project`, `Discipline`) are defined in
core/models/catalog.py; this module only decides what the metadata form
sees: active rows, in the order the selects display them.
"""

from django.db.models import QuerySet

from core.models import Discipline, Project


def list_active_projects() -> QuerySet[Project]:
    return Project.objects.filter(active=True).order_by("name", "id")


def list_active_disciplines() -> QuerySet[Discipline]:
    return Discipline.objects.filter(active=True).order_by("name", "id")
