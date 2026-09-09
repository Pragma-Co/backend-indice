"""JSON shapes of the catalog endpoints consumed by the metadata form.

The keys follow the contract agreed with the frontend (docs/API_CONTRACT.md
in the frontend repository).
"""

from core.models import Discipline, Project


def serialize_project(project: Project) -> dict:
    return {"id": project.id, "code": project.code, "name": project.name}


def serialize_discipline(discipline: Discipline) -> dict:
    return {"id": discipline.id, "acronym": discipline.acronym, "name": discipline.name}
