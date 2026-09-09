"""URL configuration for the API-6 project."""

from django.contrib import admin
from django.urls import include, path

from core.views import api_root, health_check

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
