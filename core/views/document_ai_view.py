import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.document_ai_serializer import serialize_suggestion
from core.services.document_ai_exceptions import UnsupportedFileTypeError
from core.services.document_ai_service import suggest_document_metadata
from core.services.document_exceptions import TempFileNotFoundError

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def suggest_document_metadata_view(request, temp_file_id):
    try:
        result = suggest_document_metadata(temp_file_id)
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

    return JsonResponse(serialize_suggestion(result))
