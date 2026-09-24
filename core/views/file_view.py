import logging

from django.http import FileResponse, JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

from core.services.audit_service import record_document_access_denied
from core.services.documents_exceptions import (
    AccessDeniedError,
    DocumentFileNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.file_service import get_document_file_for_view

logger = logging.getLogger(__name__)


@require_GET
@xframe_options_exempt
def document_file_view(request, file_id):
    try:
        file_obj, path = get_document_file_for_view(file_id, request.GET.get("user_id"))
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

    response = FileResponse(path.open("rb"), content_type=file_obj.mime_type)
    response["Content-Disposition"] = f'inline; filename="{file_obj.original_name}"'
    response["Cache-Control"] = "private, no-store"
    return response
