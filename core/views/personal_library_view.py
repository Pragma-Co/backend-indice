import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core.services.document_exceptions import DocumentQueryError
from core.services.personal_library_service import (
    SavedDocumentNotFoundError,
    list_saved_documents,
    remove_document,
    save_document,
)
from core.views.user_view import _active_user, _unauthorized

logger = logging.getLogger(__name__)


@require_GET
def personal_library(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    try:
        return JsonResponse(list_saved_documents(user, request.GET))
    except DocumentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list saved documents")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_http_methods(["POST", "DELETE"])
def personal_library_document(request, document_id):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    if request.method == "DELETE":
        try:
            remove_document(user, document_id)
            return HttpResponse(status=204)
        except Exception as exc:
            logger.exception("Failed to remove saved document")
            return JsonResponse({"error": type(exc).__name__}, status=500)

    try:
        _, created = save_document(user, document_id)
    except SavedDocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to save document")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse({"document_id": document_id, "saved": True}, status=201 if created else 200)
