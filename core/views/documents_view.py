import logging
import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from core.services.documents_service import (
    get_documents, 
    get_simple_filters,
    get_document_detail,
    request_document_access
)

from core.services.documents_exceptions import (
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)

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

@require_GET
def document_detail(request, document_id):
    user_id = request.GET.get("user_id")
    try:
        return JsonResponse(get_document_detail(document_id, user_id))
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to retrieve document detail")
        return JsonResponse({"error": type(exc).__name__}, status=500)

@csrf_exempt
@require_POST
def request_access(request, document_id):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    user_id = payload.get("user_id")
    justification = payload.get("justification", "")

    try:
        result = request_document_access(document_id, user_id, justification)
        return JsonResponse(result, status=201)
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except MissingUserError:
        return JsonResponse({"error": "MissingUser"}, status=400)
    except UserNotFoundError:
        return JsonResponse({"error": "UserNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to request document access")
        return JsonResponse({"error": type(exc).__name__}, status=500)
