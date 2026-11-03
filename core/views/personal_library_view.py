import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core.services.personal_library_service import (
    LibraryAccessDeniedError,
    SavedDocumentNotFoundError,
    list_saved_documents,
    remove_document,
    save_document,
)
from core.views.user_view import _active_user, _unauthorized


def _document_id(request):
    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    document_id = payload.get("document_id") if isinstance(payload, dict) else None
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        return None
    return document_id


@require_http_methods(["GET", "POST", "DELETE"])
def personal_library(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    if request.method == "GET":
        return JsonResponse(list_saved_documents(user))

    document_id = _document_id(request)
    if document_id is None:
        return JsonResponse({"error": "document_id must be an integer."}, status=400)

    if request.method == "POST":
        try:
            saved_document, created = save_document(user, document_id)
        except SavedDocumentNotFoundError:
            return JsonResponse({"error": "DocumentNotFound"}, status=404)
        except LibraryAccessDeniedError:
            return JsonResponse({"error": "AccessDenied"}, status=403)
        return JsonResponse(
            {"document_id": saved_document.document_id, "saved": True},
            status=201 if created else 200,
        )

    try:
        remove_document(user, document_id)
    except SavedDocumentNotFoundError:
        return JsonResponse({"error": "SavedDocumentNotFound"}, status=404)
    return HttpResponse(status=204)
