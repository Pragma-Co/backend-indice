from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.document_ai_serializer import serialize_suggestion
from core.services.document_ai_exceptions import AISuggestionError, UnsupportedFileTypeError
from core.services.document_ai_service import suggest_document_metadata
from core.services.document_exceptions import TempFileNotFoundError


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
    except AISuggestionError:
        return JsonResponse(
            {"error": "Failed to generate suggestions. Please try again."}, status=502
        )

    return JsonResponse(serialize_suggestion(result))
