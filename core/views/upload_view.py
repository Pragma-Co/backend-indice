from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.upload_serializer import serialize_upload_result
from core.services.temp_upload_service import store_uploaded_file
from core.services.upload_exceptions import (
    FileTooLargeError,
    InvalidFileTypeError,
    MissingFileError,
    UploadStorageError,
)

@csrf_exempt
@require_POST
def upload_document(request):
    uploaded_file = request.FILES.get("file")

    try:
        result = store_uploaded_file(uploaded_file)
    except MissingFileError:
        return JsonResponse(
            {"error": "No file was sent. Send the file in the 'file' field."},
            status=400,
        )
    except FileTooLargeError as exc:
        return JsonResponse(
            {
                "error": "File exceeds the maximum allowed size (100MB).",
                "max_size_bytes": exc.max_size_bytes,
            },
            status=413,
        )
    except InvalidFileTypeError:
        return JsonResponse(
            {
                "error": "File type not allowed or content doesn't match a supported type.",
                "allowed_types": ["pdf", "doc", "jpeg", "png"],
            },
            status=400,
        )
    except UploadStorageError:
        return JsonResponse(
            {"error": "Failed to save the file. Please try again."}, status=500
        )

    return JsonResponse(serialize_upload_result(result), status=201)

