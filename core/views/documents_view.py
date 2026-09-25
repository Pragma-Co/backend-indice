import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.serializers.document_serializer import serialize_created_document
from core.services import audit_service
from core.services.document_creation_service import create_document
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentQueryError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    TempFileNotFoundError,
)
from core.services.documents_exceptions import (
    AlreadyHasAccessError,
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.documents_service import (
    get_document_detail,
    get_documents,
    get_simple_filters,
    request_document_access,
)

logger = logging.getLogger(__name__)


@require_GET
def documents(request):
    try:
        return JsonResponse(get_documents(request.GET))
    except DocumentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list documents")
        return JsonResponse({"error": type(exc).__name__}, status=500)


def create_document_view(request):
    try:
        payload = json.loads(request.body or b"")
    except ValueError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

    try:
        document = create_document(payload)
    except DocumentValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except TempFileNotFoundError:
        return JsonResponse(
            {
                "errors": {
                    "temp_file_id": {
                        "code": "not_found",
                        "message": "Uploaded file not found or expired. Upload it again.",
                    }
                }
            },
            status=404,
        )
    except DuplicateDocumentFileError as exc:
        audit_service.log_duplicate_attempt(
            request,
            exc.existing_file,
            audit_service.STAGE_SUBMIT,
            {
                "temp_file_id": payload.get("temp_file_id")
                or (payload.get("temp_file_ids") or [None])[0],
                "temp_file_ids": payload.get("temp_file_ids") or [payload.get("temp_file_id")],
            },
            payload,
        )
        return JsonResponse(
            {
                "error": "This file is already registered.",
                "document": {"id": exc.document.id, "code": exc.document.code},
            },
            status=409,
        )
    except DocumentStorageError:
        return JsonResponse({"error": "Failed to store the file. Please try again."}, status=500)
    except DocumentCodeCollisionError:
        return JsonResponse(
            {"error": "Could not generate a unique code. Please try again."}, status=503
        )
    except Exception as exc:
        logger.exception("Failed to create document")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    audit_service.log_document_submitted(request, document, payload)

    return JsonResponse(serialize_created_document(document), status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def documents_collection(request):
    if request.method == "POST":
        return create_document_view(request)
    return documents(request)


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
        audit_service.log_access_requested(
            request, document_id, "", user_id, justification, result["created"]
        )
        return JsonResponse(result, status=201)
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except MissingUserError:
        return JsonResponse({"error": "MissingUser"}, status=400)
    except UserNotFoundError:
        return JsonResponse({"error": "UserNotFound"}, status=404)
    except AlreadyHasAccessError:
        return JsonResponse({"error": "AlreadyHasAccess"}, status=409)
    except Exception as exc:
        logger.exception("Failed to request document access")
        return JsonResponse({"error": type(exc).__name__}, status=500)
