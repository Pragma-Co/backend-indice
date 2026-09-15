import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services.documents_service import get_documents, get_simple_filters

logger = logging.getLogger(__name__)


@require_GET
def documents(request):
    try:
        return JsonResponse({"documents": get_documents(request.GET)})
    except Exception as exc:
        logger.exception("Failed to list documents")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_GET
def simple_filters(request):
    try:
        return JsonResponse(get_simple_filters())
    except Exception as exc:
        logger.exception("Failed to retrieve simple filters")
        return JsonResponse({"error": type(exc).__name__}, status=500)
