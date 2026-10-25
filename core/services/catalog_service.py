from django.db.models import QuerySet

from core.models import Area, Discipline, Document, DocumentType, Project


def list_project_discipline_ids(project_ids) -> dict[int, list[int]]:
    rows = (
        Document.objects.filter(project_id__in=project_ids, discipline__active=True)
        .values_list("project_id", "discipline_id")
        .distinct()
        .order_by("project_id", "discipline_id")
    )
    discipline_ids: dict[int, list[int]] = {project_id: [] for project_id in project_ids}
    for project_id, discipline_id in rows:
        discipline_ids[project_id].append(discipline_id)
    return discipline_ids


def list_active_projects() -> list[Project]:
    projects = list(Project.objects.filter(active=True).order_by("name", "id"))
    discipline_ids = list_project_discipline_ids([project.id for project in projects])
    for project in projects:
        project.discipline_ids = discipline_ids[project.id]
    return projects


def list_active_disciplines() -> QuerySet[Discipline]:
    return Discipline.objects.filter(active=True).order_by("name", "id")


def list_active_document_types() -> QuerySet[DocumentType]:
    return DocumentType.objects.filter(active=True).order_by("name", "id")


def list_active_areas() -> QuerySet[Area]:
    return Area.objects.filter(active=True).order_by("name", "id")
