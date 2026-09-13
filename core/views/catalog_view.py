"""Read-only catalog endpoints that populate the selects of the metadata form."""

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.serializers.catalog_serializer import serialize_discipline, serialize_project
from core.services.catalog_service import list_active_disciplines, list_active_projects

logger = logging.getLogger(__name__)


def _respond_list(request, query, serialize, resource: str) -> JsonResponse:
    try:
        data = [serialize(item) for item in query()]
    except Exception as exc:
        # Full details go to the server log only; error strings can contain
        # hosts, credentials or SQL (LGPD)
        logger.exception("Failed to list %s", resource)
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse(data, safe=False)


# csrf_exempt: read-only endpoints consumed by the SPA without a session; without it
# the CSRF middleware would answer 403 to other methods before require_GET returns 405
@csrf_exempt
@require_GET
def list_projects(request):
    """GET /projects/ -> active projects ordered by name."""
    return _respond_list(request, list_active_projects, serialize_project, "projects")


@csrf_exempt
@require_GET
def list_disciplines(request):
    """GET /disciplines/ -> active disciplines ordered by name."""
    return _respond_list(request, list_active_disciplines, serialize_discipline, "disciplines")
