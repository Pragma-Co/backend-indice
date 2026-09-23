"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.api_root_view import api_root
from core.views.catalog_view import list_disciplines, list_projects, list_document_types
from core.views.document_ai_view import suggest_document_metadata_view
from core.views.documents_view import (
    document_detail,
    documents_collection,
    request_access,
    simple_filters,
)
from core.views.health_view import health_check
from core.views.upload_view import upload_document

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("documents", documents_collection, name="document-list"),
    path("documents/upload", upload_document, name="document-upload"),
    path("documents/simple-filters", simple_filters, name="document-simple-filters"),
    path("documents/<int:document_id>", document_detail, name="document-detail"),
    path(
        "documents/<int:document_id>/request-access", request_access, name="document-request-access"
    ),
    path(
        "documents/<str:temp_file_id>/suggestions",
        suggest_document_metadata_view,
        name="document-ai-suggestions",
    ),
    path("projects/", list_projects, name="project-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
    path("documents/types", list_document_types, name="document-type-list")
]
