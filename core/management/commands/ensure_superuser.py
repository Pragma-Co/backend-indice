"""Idempotent creation of the default admin user.

Runs on every container start (see docker-compose.yml): creates the
superuser defined by the DJANGO_SUPERUSER_* environment variables if it
does not exist yet, and does nothing otherwise.

The user model logs in by email, so DJANGO_SUPERUSER_EMAIL identifies the
account and DJANGO_SUPERUSER_USERNAME is used as the display name. Every user
belongs to an area, so a default one is created alongside the first admin.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Area

DEFAULT_AREA_ACRONYM = "ADM"
DEFAULT_AREA_NAME = "Administration"


class Command(BaseCommand):
    help = "Create the default superuser from DJANGO_SUPERUSER_* env vars if missing."

    @transaction.atomic
    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        name = os.environ.get("DJANGO_SUPERUSER_USERNAME") or "Administrator"

        if not email or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipping superuser creation."
            )
            return

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"Superuser '{email}' already exists; nothing to do.")
            return

        area, created = Area.objects.get_or_create(
            acronym=DEFAULT_AREA_ACRONYM, defaults={"name": DEFAULT_AREA_NAME}
        )
        if created:
            self.stdout.write(f"Area '{area.acronym}' created for the admin user.")

        User.objects.create_superuser(
            email=email, password=password, name=name, area=area
        )
        self.stdout.write(self.style.SUCCESS(f"Superuser '{email}' created."))
