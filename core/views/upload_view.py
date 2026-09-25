from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.serializers.upload_serializer import (
    serialize_duplicate_result,
    serialize_revision_result,
    serialize_upload_result,
)
from core.services import audit_service
from core.services.temp_upload_service import store_uploaded_file
from core.services.upload_exceptions import (
    DuplicateFileError,
    FileTooLargeError,
    InvalidFileTypeError,
    MissingFileError,
    UploadStorageError,
)


@csrf_exempt
@require_POST
def upload_document(request):
    uploaded_file = request.FILES.get("file")
    force_new_revision = request.POST.get("force_new_revision") == "true"

    try:
        result = store_uploaded_file(uploaded_file, force_new_revision=force_new_revision)
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
    except DuplicateFileError as exc:
        audit_service.log_duplicate_attempt(
            request,
            exc.existing_file,
            audit_service.STAGE_UPLOAD,
            {"original_name": uploaded_file.name},
        )
        return JsonResponse(serialize_duplicate_result(exc), status=409)
    except UploadStorageError:
        return JsonResponse({"error": "Failed to save the file. Please try again."}, status=500)

    audit_service.log_temp_upload(request, result)

    if result.get("revision_created"):
        return JsonResponse(serialize_revision_result(result), status=201)

    return JsonResponse(serialize_upload_result(result), status=201)
