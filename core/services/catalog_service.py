from django.db.models import Prefetch, QuerySet

from core.models import Area, Discipline, DocumentType, Project


def list_active_projects() -> QuerySet[Project]:
    active_disciplines = Discipline.objects.filter(active=True).order_by("id")
    return (
        Project.objects.filter(active=True)
        .prefetch_related(Prefetch("disciplines", queryset=active_disciplines))
        .order_by("name", "id")
    )


def list_active_disciplines() -> QuerySet[Discipline]:
    return Discipline.objects.filter(active=True).order_by("name", "id")


def list_active_document_types() -> QuerySet[DocumentType]:
    return DocumentType.objects.filter(active=True).order_by("name", "id")


def list_active_areas() -> QuerySet[Area]:
    return Area.objects.filter(active=True).order_by("name", "id")
