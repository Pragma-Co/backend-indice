import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.serializers.document_serializer import serialize_created_document
from core.services.document_creation_service import create_document
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentQueryError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    TempFileNotFoundError,
)
from core.services.documents_service import get_documents, get_simple_filters

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
