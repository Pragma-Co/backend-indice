import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core.models import AuditAction
from core.serializers.access_request_serializer import (
    serialize_access_decision,
    serialize_pending_access_page,
)
from core.services import audit_service
from core.services.access_request_exceptions import (
    AccessRequestAlreadyDecidedError,
    AccessRequestNotFoundError,
    AccessRequestValidationError,
    OwnAccessRequestReviewError,
)
from core.services.access_request_service import (
    decide_access_request,
    is_access_approver,
    list_pending_access_requests,
)

logger = logging.getLogger(__name__)

ENTITY_DOCUMENT_ACCESS = "document_access"


def _approver_or_error(request):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return None, JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if not is_access_approver(user):
        return None, JsonResponse({"error": "PermissionDenied"}, status=403)
    return user, None


@require_GET
def pending_access_requests_view(request):
    approver, error_response = _approver_or_error(request)
    if error_response is not None:
        return error_response
    try:
        page = list_pending_access_requests(approver, request.GET)
        return JsonResponse(serialize_pending_access_page(page))
    except AccessRequestValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list pending access requests")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_POST
def access_request_decision_view(request, access_id):
    approver, error_response = _approver_or_error(request)
    if error_response is not None:
        return error_response
    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    try:
        access = decide_access_request(access_id, approver, payload)
    except AccessRequestValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except AccessRequestNotFoundError:
        return JsonResponse({"error": "AccessRequestNotFound"}, status=404)
    except OwnAccessRequestReviewError:
        return JsonResponse({"error": "CannotReviewOwnAccessRequest"}, status=403)
    except AccessRequestAlreadyDecidedError as exc:
        return JsonResponse(
            {"error": "AccessRequestAlreadyDecided", "status": exc.status}, status=409
        )
    except Exception as exc:
        logger.exception("Failed to record access request decision")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    audit_service.log_event(
        request,
        AuditAction.UPDATE,
        ENTITY_DOCUMENT_ACCESS,
        access.pk,
        {
            "event": f"ACCESS_{access.status}",
            "document_id": access.document_id,
            "document_code": access.document.code,
            "requester_id": access.user_id,
        },
    )
    return JsonResponse(serialize_access_decision(access))
