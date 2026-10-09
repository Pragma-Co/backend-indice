"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.api_root_view import api_root
from core.views.catalog_view import list_disciplines, list_document_types, list_projects
from core.views.document_ai_view import suggest_document_metadata_view
from core.views.documents_view import (
    create_revision_view,
    document_resource,
    documents_collection,
    request_access,
    simple_filters,
)
from core.views.file_view import document_file_view
from core.views.health_view import health_check
from core.views.revision_review_view import pending_revisions_view, revision_decision_view
from core.views.upload_view import upload_document
from core.views.user_view import request_user_deletion, user_me

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("users/me", user_me, name="user-me"),
    path(
        "users/me/request-deletion",
        request_user_deletion,
        name="user-deletion-request",
    ),
    path("documents", documents_collection, name="document-list"),
    path("documents/upload", upload_document, name="document-upload"),
    path("documents/simple-filters", simple_filters, name="document-simple-filters"),
    path("documents/<int:document_id>", document_resource, name="document-detail"),
    path(
        "documents/<int:document_id>/revisions",
        create_revision_view,
        name="document-revision-create",
    ),
    path(
        "documents/<int:document_id>/request-access", request_access, name="document-request-access"
    ),
    path(
        "documents/<str:temp_file_id>/suggestions",
        suggest_document_metadata_view,
        name="document-ai-suggestions",
    ),
    path("manager/pending-revisions", pending_revisions_view, name="manager-pending-revisions"),
    path(
        "manager/revisions/<int:revision_id>/decision",
        revision_decision_view,
        name="manager-revision-decision",
    ),
    path("files/<int:file_id>/view", document_file_view, name="document-file-view"),
    path("projects/", list_projects, name="project-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
    path("documents/types", list_document_types, name="document-type-list"),
]
