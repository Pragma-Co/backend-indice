"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.api_root_view import api_root
from core.views.catalog_view import list_disciplines, list_projects
from core.views.document_create_view import documents_collection
from core.views.documents_view import simple_filters
from core.views.health_view import health_check
from core.views.upload_view import upload_document

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("documents", documents_collection, name="document-list"),
    path("documents/upload", upload_document, name="document-upload"),
    path("documents/simple-filters", simple_filters, name="document-simple-filters"),
    path("projects/", list_projects, name="project-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
]
