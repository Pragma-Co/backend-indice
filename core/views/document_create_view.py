"""POST /documents: confirmation step of the registration flow."""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.serializers.document_serializer import serialize_created_document
from core.services.document_creation_service import create_document
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    TempFileNotFoundError,
)
from core.views.documents_view import documents as list_documents

logger = logging.getLogger(__name__)


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
            {"errors": {"temp_file_id": "Uploaded file not found or expired. Upload it again."}},
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
        # Full details go to the server log only (LGPD)
        logger.exception("Failed to create document")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    return JsonResponse(serialize_created_document(document), status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def documents_collection(request):
    """GET lists documents (see documents_view); POST registers a new one."""
    if request.method == "POST":
        return create_document_view(request)
    return list_documents(request)
