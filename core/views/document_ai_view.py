import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.document_ai_serializer import serialize_suggestion
from core.services import audit_service
from core.services.document_ai_exceptions import UnsupportedFileTypeError
from core.services.document_ai_service import classify_document_metadata
from core.services.document_exceptions import TempFileNotFoundError
from core.services.document_search_summary_service import (
    MAX_REQUEST_BYTES,
    InvalidSearchSummaryInput,
    summarize_search,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def suggest_document_metadata_view(request, temp_file_id):
    try:
        result, classification = classify_document_metadata(temp_file_id)
    except TempFileNotFoundError:
        return JsonResponse({"error": "Temporary file not found."}, status=404)
    except UnsupportedFileTypeError:
        return JsonResponse(
            {
                "error": "Automatic suggestions are only available for PDF and DOCX files.",
                "supported_types": ["pdf", "docx"],
            },
            status=422,
        )
    except Exception as exc:
        logger.exception("Document metadata suggestion failed")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    audit_service.log_ai_classification(request, temp_file_id, classification)
    return JsonResponse(serialize_suggestion(result))


@csrf_exempt
@require_POST
def summarize_search_view(request):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return JsonResponse({"error": "InvalidContentLength"}, status=400)
    if content_length > MAX_REQUEST_BYTES:
        return JsonResponse({"error": "PayloadTooLarge"}, status=413)

    body = request.body
    if len(body) > MAX_REQUEST_BYTES:
        return JsonResponse({"error": "PayloadTooLarge"}, status=413)

    try:
        payload = json.loads(body or b"")
    except ValueError:
        return JsonResponse({"error": "InvalidJSON"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "InvalidInput"}, status=400)

    try:
        result = summarize_search(payload.get("query"), payload.get("snippets"))
    except InvalidSearchSummaryInput:
        return JsonResponse({"error": "InvalidInput"}, status=400)
    except Exception as exc:
        logger.exception("Search summary failed")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    return JsonResponse(result)
