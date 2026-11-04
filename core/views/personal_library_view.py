from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core.services.document_exceptions import DocumentQueryError
from core.services.personal_library_service import (
    LibraryAccessDeniedError,
    SavedDocumentNotFoundError,
    list_saved_documents,
    remove_document,
    save_document,
)
from core.views.user_view import _active_user, _unauthorized


@require_GET
def personal_library(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    try:
        return JsonResponse(list_saved_documents(user, request.GET))
    except DocumentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)


@require_http_methods(["POST", "DELETE"])
def personal_library_document(request, document_id):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    if request.method == "DELETE":
        remove_document(user, document_id)
        return HttpResponse(status=204)

    try:
        _, created = save_document(user, document_id)
    except SavedDocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except LibraryAccessDeniedError:
        return JsonResponse({"error": "AccessDenied"}, status=403)
    return JsonResponse({"document_id": document_id, "saved": True}, status=201 if created else 200)
