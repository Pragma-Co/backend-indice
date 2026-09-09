"""Idempotent seed of the development catalogs (projects and disciplines).

Safe to run any number of times: entries are matched by their natural key
(project code / discipline name) and only created when missing, so
edits made through the admin are never overwritten.

Usage (inside the container): docker compose exec api python manage.py seed_catalogs
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Discipline, Project

DEFAULT_PROJECTS = [
    {"code": "PJT001", "name": "Projeto Alfa"},
    {"code": "PJT002", "name": "Projeto Beta"},
    {"code": "PJT003", "name": "Projeto Gama"},
]

# Acronyms are derived by Discipline.save() from the first three letters of the name
DEFAULT_DISCIPLINES = [
    "Engenharia",
    "Manufatura",
    "Qualidade",
    "Configuração",
    "Tubulação",
    "Estrutura",
    "Elétrica",
]


class Command(BaseCommand):
    help = "Create the default projects and disciplines for development if missing."

    @transaction.atomic
    def handle(self, *args, **options):
        created = {"projects": 0, "disciplines": 0}

        for data in DEFAULT_PROJECTS:
            _, was_created = Project.objects.get_or_create(
                code=data["code"], defaults={"name": data["name"]}
            )
            created["projects"] += int(was_created)

        for name in DEFAULT_DISCIPLINES:
            _, was_created = Discipline.objects.get_or_create(name=name)
            created["disciplines"] += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed finished: {projects} project(s) and {disciplines} discipline(s) "
                "created.".format(**created)
            )
        )
