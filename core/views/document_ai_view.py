import json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.document_ai_serializer import serialize_suggestion
from core.services import audit_service
from core.services.document_ai_exceptions import UnsupportedFileTypeError
from core.services.document_ai_service import (
    classify_document_metadata,
    prepare_suggestion,
    stream_suggestion_events,
)
from core.services.document_exceptions import DocumentQueryError, TempFileNotFoundError
from core.services.document_search_summary_service import (
    MAX_REQUEST_BYTES,
    InvalidSearchSummaryInput,
    summarize_search,
    summarize_search_results,
)

logger = logging.getLogger(__name__)


NDJSON_CONTENT_TYPE = "application/x-ndjson"


def _suggestion_failure_response(exc: Exception) -> JsonResponse:
    if isinstance(exc, TempFileNotFoundError):
        return JsonResponse({"error": "Temporary file not found."}, status=404)
    if isinstance(exc, UnsupportedFileTypeError):
        return JsonResponse(
            {
                "error": "Automatic suggestions are only available for PDF and DOCX files.",
                "supported_types": ["pdf", "docx"],
            },
            status=422,
        )
    logger.exception("Document metadata suggestion failed")
    return JsonResponse({"error": type(exc).__name__}, status=500)


@csrf_exempt
@require_POST
def suggest_document_metadata_view(request, temp_file_id):
    try:
        result, classification = classify_document_metadata(temp_file_id)
    except Exception as exc:
        return _suggestion_failure_response(exc)

    audit_service.log_ai_classification(request, temp_file_id, classification)
    return JsonResponse(serialize_suggestion(result))


def _ndjson_line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _suggestion_event_lines(events):
    try:
        for event in events:
            if "suggestion" in event:
                event = {**event, "suggestion": serialize_suggestion(event["suggestion"])}
            yield _ndjson_line(event)
    except Exception as exc:
        logger.exception("Document metadata suggestion stream failed")
        yield _ndjson_line({"type": "error", "error": type(exc).__name__})


@csrf_exempt
@require_POST
def stream_document_suggestions_view(request, temp_file_id):
    try:
        prepared = prepare_suggestion(temp_file_id)
    except Exception as exc:
        return _suggestion_failure_response(exc)

    audit_service.log_ai_classification(request, temp_file_id, prepared.classification)
    response = StreamingHttpResponse(
        _suggestion_event_lines(stream_suggestion_events(temp_file_id, prepared)),
        content_type=NDJSON_CONTENT_TYPE,
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


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
        if "snippets" in payload:
            result = summarize_search(payload.get("query"), payload.get("snippets"))
        else:
            user = (
                request.user if request.user.is_authenticated and request.user.is_active else None
            )
            result = summarize_search_results(payload.get("filters"), user)
    except InvalidSearchSummaryInput:
        return JsonResponse({"error": "InvalidInput"}, status=400)
    except DocumentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Search summary failed")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    return JsonResponse(result)
