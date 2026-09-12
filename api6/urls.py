"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import path

from core.views.api_root_view import api_root
from core.views.documents_view import documents, simple_filters
from core.views.health_view import health_check
from core.views.upload_view import upload_document

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("documents", documents, name="document-list"),
    path("documents/upload", upload_document, name="document-upload"),
    path("documents/simple-filters", simple_filters, name="document-simple-filters"),
]
