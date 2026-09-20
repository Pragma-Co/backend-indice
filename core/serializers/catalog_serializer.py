from core.models import Discipline, Project


def serialize_project(project: Project) -> dict:
    return {
        "id": project.id,
        "code": project.code,
        "name": project.name,
        "discipline_ids": [discipline.id for discipline in project.disciplines.all()],
    }


def serialize_discipline(discipline: Discipline) -> dict:
    return {"id": discipline.id, "code": discipline.code, "name": discipline.name}
