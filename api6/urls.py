"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.access_group_view import (
    access_group_options_view,
    access_group_user_view,
    access_group_users_view,
    access_groups_view,
)
from core.views.access_request_view import (
    access_request_decision_view,
    access_request_detail_view,
    pending_access_requests_view,
)
from core.views.api_root_view import api_root
from core.views.auth_view import csrf_view, login_view, logout_view
from core.views.catalog_view import list_areas, list_disciplines, list_document_types, list_projects
from core.views.document_ai_view import (
    stream_document_suggestions_view,
    suggest_document_metadata_view,
    summarize_search_view,
)
from core.views.documents_view import (
    archived_documents_view,
    create_revision_view,
    document_recommendations_view,
    document_resource,
    document_security_event_view,
    documents_collection,
    request_access,
    restore_document_view,
    search_documents_view,
    simple_filters,
)
from core.views.file_view import document_file_view
from core.views.health_view import health_check
from core.views.legal_consent_view import (
    current_legal_version_view,
    legal_acceptances_view,
    legal_documents_view,
    legal_version_view,
    revoke_legal_acceptance_view,
)
from core.views.manager_activity_view import manager_activities_view
from core.views.notification_view import (
    notification_read_view,
    notifications_read_all_view,
    notifications_view,
)
from core.views.personal_library_view import personal_library, personal_library_document
from core.views.revision_review_view import pending_revisions_view, revision_decision_view
from core.views.search_history_view import search_history_view
from core.views.upload_view import upload_document
from core.views.user_view import request_user_deletion, user_me, users_collection

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("auth/csrf", csrf_view, name="auth-csrf"),
    path("auth/login", login_view, name="auth-login"),
    path("auth/logout", logout_view, name="auth-logout"),
    path("users", users_collection, name="user-list"),
    path("users/me", user_me, name="user-me"),
    path("users/me/search-history", search_history_view, name="user-search-history"),
    path("users/me/library", personal_library, name="personal-library"),
    path(
        "users/me/library/<int:document_id>",
        personal_library_document,
        name="personal-library-document",
    ),
    path(
        "users/me/request-deletion",
        request_user_deletion,
        name="user-deletion-request",
    ),
    path("users/me/legal-acceptances", legal_acceptances_view, name="user-legal-acceptances"),
    path(
        "users/me/legal-acceptances/<int:acceptance_id>/revoke",
        revoke_legal_acceptance_view,
        name="user-legal-acceptance-revoke",
    ),
    path("legal-documents", legal_documents_view, name="legal-document-list"),
    path(
        "legal-documents/versions/<int:version_id>",
        legal_version_view,
        name="legal-version-detail",
    ),
    path(
        "legal-documents/<slug:slug>/current",
        current_legal_version_view,
        name="legal-document-current",
    ),
    path("documents", documents_collection, name="document-list"),
    path("documents/upload", upload_document, name="document-upload"),
    path("documents/simple-filters", simple_filters, name="document-simple-filters"),
    path("documents/search", search_documents_view, name="document-search"),
    path(
        "documents/search/ai-summary",
        summarize_search_view,
        name="document-search-ai-summary",
    ),
    path("documents/archived", archived_documents_view, name="document-archived-list"),
    path("documents/<int:document_id>", document_resource, name="document-detail"),
    path("documents/<int:document_id>/restore", restore_document_view, name="document-restore"),
    path(
        "documents/<int:document_id>/recommendations",
        document_recommendations_view,
        name="document-recommendations",
    ),
    path(
        "documents/<int:document_id>/revisions",
        create_revision_view,
        name="document-revision-create",
    ),
    path(
        "documents/<int:document_id>/request-access", request_access, name="document-request-access"
    ),
    path(
        "documents/<int:document_id>/security-events",
        document_security_event_view,
        name="document-security-event",
    ),
    path(
        "documents/<str:temp_file_id>/suggestions",
        suggest_document_metadata_view,
        name="document-ai-suggestions",
    ),
    path(
        "documents/<str:temp_file_id>/suggestions/stream",
        stream_document_suggestions_view,
        name="document-ai-suggestions-stream",
    ),
    path("manager/activities", manager_activities_view, name="manager-activities"),
    path("access-groups", access_group_options_view, name="access-group-options"),
    path("manager/access-groups", access_groups_view, name="manager-access-groups"),
    path(
        "manager/access-groups/<int:group_id>/users",
        access_group_users_view,
        name="manager-access-group-users",
    ),
    path(
        "manager/access-groups/<int:group_id>/users/<int:user_id>",
        access_group_user_view,
        name="manager-access-group-user",
    ),
    path("manager/pending-revisions", pending_revisions_view, name="manager-pending-revisions"),
    path(
        "manager/revisions/<int:revision_id>/decision",
        revision_decision_view,
        name="manager-revision-decision",
    ),
    path(
        "manager/pending-access-requests",
        pending_access_requests_view,
        name="manager-pending-access-requests",
    ),
    path(
        "manager/access-requests/<int:access_id>",
        access_request_detail_view,
        name="manager-access-request-detail",
    ),
    path(
        "manager/access-requests/<int:access_id>/decision",
        access_request_decision_view,
        name="manager-access-request-decision",
    ),
    path("notifications", notifications_view, name="notification-list"),
    path("notifications/read-all", notifications_read_all_view, name="notification-read-all"),
    path(
        "notifications/<int:notification_id>/read",
        notification_read_view,
        name="notification-read",
    ),
    path("files/<int:file_id>/view", document_file_view, name="document-file-view"),
    path("projects/", list_projects, name="project-list"),
    path("areas/", list_areas, name="area-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
    path("documents/types", list_document_types, name="document-type-list"),
]
