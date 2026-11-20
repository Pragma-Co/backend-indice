import logging

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET

from core.services.audit_service import record_capture_attempt, record_document_access_denied
from core.services.documents_exceptions import (
    AccessDeniedError,
    DocumentFileNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.file_service import get_document_file_for_view

logger = logging.getLogger(__name__)


def _viewer_id(request):
    if request.user.is_authenticated:
        return request.user.id
    if settings.DEBUG:
        return request.GET.get("user_id")
    return None


def _is_embedded_or_navigated(request):
    """The SPA reads files with fetch() (Sec-Fetch-Dest: empty).

    Any other destination means the file URL was opened in a tab, frame,
    <embed> or similar, outside the controlled viewer.
    """
    destination = request.headers.get("Sec-Fetch-Dest")
    return destination is not None and destination != "empty"


@require_GET
def document_file_view(request, file_id):
    try:
        file_obj, path = get_document_file_for_view(file_id, _viewer_id(request))
    except DocumentFileNotFoundError:
        return JsonResponse({"error": "FileNotFound"}, status=404)
    except MissingUserError:
        return JsonResponse({"error": "MissingUser"}, status=400)
    except UserNotFoundError:
        return JsonResponse({"error": "UserNotFound"}, status=404)
    except AccessDeniedError as exc:
        document, user = exc.args
        record_document_access_denied(document, user, request)
        return JsonResponse({"error": "AccessDenied"}, status=403)
    except Exception as exc:
        logger.exception("Failed to serve document file")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    if _is_embedded_or_navigated(request):
        document = file_obj.revision.document
        record_capture_attempt(
            request,
            document,
            "DIRECT_FILE_NAVIGATION",
            file_id=file_obj.id,
            detail=request.headers.get("Sec-Fetch-Dest"),
        )
        return JsonResponse({"error": "DirectAccessForbidden"}, status=403)

    response = FileResponse(path.open("rb"), content_type=file_obj.mime_type)
    response["Content-Disposition"] = f'inline; filename="{file_obj.original_name}"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    return response
