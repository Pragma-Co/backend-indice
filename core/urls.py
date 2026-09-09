"""Routes of the core app, mounted at the project root (see api6/urls.py).

The Vue frontend calls them through a Vite proxy that strips the /api
prefix, so the browser's GET /api/projects/ reaches Django as GET /projects/.
"""

from django.urls import path

from core.views import list_disciplines, list_projects

urlpatterns = [
    path("projects/", list_projects, name="project-list"),
    path("disciplines/", list_disciplines, name="discipline-list"),
]
