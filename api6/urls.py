"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.api_root_view import api_root
from core.views.catalog_view import list_disciplines, list_projects
from core.views.health_view import health_check
from core.views.upload_view import upload_document

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("documents/upload", upload_document, name="document-upload"),
    # Catalogs for the metadata form selects; the Vite proxy strips the /api prefix
    path("projects/", list_projects, name="project-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
]
