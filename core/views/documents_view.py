import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import AuditAction
from core.serializers.document_serializer import (
    serialize_archived_document,
    serialize_created_document,
    serialize_restored_document,
)
from core.services import audit_service
from core.services.document_archive_service import (
    archive_document,
    is_manager,
    list_archived_documents,
    restore_document,
)
from core.services.document_creation_service import (
    create_document,
    create_document_revision,
    submit_document_revision,
)
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentQueryError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    DuplicateRevisionUploadError,
    TempFileNotFoundError,
)
from core.services.documents_exceptions import (
    AlreadyHasAccessError,
    ArchivePermissionDeniedError,
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
from core.services.upload_exceptions import (
    DuplicateFileError,
    FileTooLargeError,
    InvalidFileTypeError,
    MissingFileError,
    UploadStorageError,
)

logger = logging.getLogger(__name__)

ENTITY_DOCUMENT = "document"


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


@csrf_exempt
@require_POST
def create_revision_view(request, document_id):
    payload = {}
    try:
        if request.content_type == "multipart/form-data":
            payload = request.POST.dict()
            revision, temp_file_ids = submit_document_revision(
                document_id, request.FILES.getlist("file"), payload.get("change_description")
            )
        else:
            payload = json.loads(request.body or "{}")
            temp_file_ids = payload.get("temp_file_ids")
            if temp_file_ids is None:
                temp_file_ids = payload.get("temp_file_id")
            revision = create_document_revision(
                document_id, temp_file_ids, payload.get("change_description")
            )
        audit_service.log_document_revision_created(request, revision, temp_file_ids)
        return JsonResponse(
            {
                "id": revision.id,
                "document_id": revision.document_id,
                "version": revision.version,
                "status": revision.status,
                "change_description": revision.change_description,
            },
            status=201,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)
    except DocumentValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except TempFileNotFoundError:
        return JsonResponse({"error": "TempFileNotFound"}, status=404)
    except DuplicateDocumentFileError as exc:
        audit_service.log_duplicate_attempt(
            request,
            exc.existing_file,
            audit_service.STAGE_SUBMIT,
            {"temp_file_ids": payload.get("temp_file_ids") or [payload.get("temp_file_id")]},
            payload,
        )
        return JsonResponse(
            {
                "error": "This file is already registered.",
                "document": {"id": exc.document.id, "code": exc.document.code},
            },
            status=409,
        )
    except DuplicateFileError as exc:
        audit_service.log_duplicate_attempt(
            request,
            exc.existing_file,
            audit_service.STAGE_UPLOAD,
            {"original_names": [file.name for file in request.FILES.getlist("file")]},
            payload,
        )
        return JsonResponse(
            {
                "error": "This file is already registered.",
                "document": {"id": exc.document_id, "code": exc.codigo_ra},
            },
            status=409,
        )
    except DuplicateRevisionUploadError as exc:
        return JsonResponse(
            {"error": "DuplicateFileInRevision", "filename": exc.filename}, status=409
        )
    except MissingFileError:
        return JsonResponse({"error": "MissingFile"}, status=400)
    except InvalidFileTypeError:
        return JsonResponse({"error": "InvalidFileType"}, status=400)
    except FileTooLargeError as exc:
        return JsonResponse(
            {"error": "FileTooLarge", "max_size_bytes": exc.max_size_bytes}, status=413
        )
    except (DocumentStorageError, UploadStorageError):
        return JsonResponse({"error": "Failed to store the file."}, status=500)
    except Exception as exc:
        logger.exception("Failed to create document revision")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_GET
def document_detail(request, document_id):
    user_id = request.user.id if request.user.is_authenticated else None
    if user_id is None and settings.DEBUG:
        user_id = request.GET.get("user_id")
    try:
        return JsonResponse(get_document_detail(document_id, user_id))
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to retrieve document detail")
        return JsonResponse({"error": type(exc).__name__}, status=500)


def _session_user(request):
    user = request.user
    if user.is_authenticated and user.is_active:
        return user, None
    return None, JsonResponse({"error": "AuthenticationRequired"}, status=401)


def _document_areas(document):
    return list(document.areas.order_by("acronym").values_list("acronym", flat=True))


def archive_document_view(request, document_id):
    user, error_response = _session_user(request)
    if error_response is not None:
        return error_response

    try:
        document = archive_document(document_id, user)
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except ArchivePermissionDeniedError:
        return JsonResponse({"error": "PermissionDenied"}, status=403)
    except Exception as exc:
        logger.exception("Failed to archive document")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    audit_service.log_event(
        request,
        AuditAction.DELETE,
        ENTITY_DOCUMENT,
        document.pk,
        {
            "event": "DOCUMENT_ARCHIVED",
            "document_code": document.code,
            "areas": _document_areas(document),
        },
    )
    return JsonResponse(serialize_archived_document(document))


@require_http_methods(["GET", "DELETE"])
def document_resource(request, document_id):
    if request.method == "DELETE":
        return archive_document_view(request, document_id)
    return document_detail(request, document_id)


@require_GET
def archived_documents_view(request):
    user, error_response = _session_user(request)
    if error_response is not None:
        return error_response
    if not is_manager(user):
        return JsonResponse({"error": "PermissionDenied"}, status=403)

    try:
        return JsonResponse(list_archived_documents(user, request.GET))
    except DocumentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list archived documents")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_POST
def restore_document_view(request, document_id):
    user, error_response = _session_user(request)
    if error_response is not None:
        return error_response

    try:
        document = restore_document(document_id, user)
    except DocumentNotFoundError:
        return JsonResponse({"error": "DocumentNotFound"}, status=404)
    except ArchivePermissionDeniedError:
        return JsonResponse({"error": "PermissionDenied"}, status=403)
    except Exception as exc:
        logger.exception("Failed to restore document")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    audit_service.log_event(
        request,
        AuditAction.UPDATE,
        ENTITY_DOCUMENT,
        document.pk,
        {
            "event": "DOCUMENT_RESTORED",
            "document_code": document.code,
            "areas": _document_areas(document),
        },
    )
    return JsonResponse(serialize_restored_document(document))


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
