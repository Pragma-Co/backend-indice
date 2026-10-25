import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import AuditAction
from core.serializers.revision_review_serializer import (
    serialize_pending_page,
    serialize_revision_decision,
)
from core.services import audit_service
from core.services.revision_review_exceptions import (
    OutdatedRevisionError,
    OwnRevisionReviewError,
    RevisionAlreadyDecidedError,
    RevisionNotFoundError,
    RevisionReviewValidationError,
)
from core.services.revision_review_service import (
    decide_revision,
    is_revision_reviewer,
    list_pending_revisions,
)

logger = logging.getLogger(__name__)

ENTITY_REVISION = "revision"


def _reviewer_or_error(request):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return None, JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if not is_revision_reviewer(user):
        return None, JsonResponse({"error": "PermissionDenied"}, status=403)
    return user, None


@csrf_exempt
@require_GET
def pending_revisions_view(request):
    _reviewer, error_response = _reviewer_or_error(request)
    if error_response is not None:
        return error_response
    try:
        return JsonResponse(serialize_pending_page(list_pending_revisions(request.GET)))
    except RevisionReviewValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list pending revisions")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@csrf_exempt
@require_POST
def revision_decision_view(request, revision_id):
    reviewer, error_response = _reviewer_or_error(request)
    if error_response is not None:
        return error_response
    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    try:
        revision, superseded = decide_revision(revision_id, reviewer, payload)
    except RevisionReviewValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except RevisionNotFoundError:
        return JsonResponse({"error": "RevisionNotFound"}, status=404)
    except OwnRevisionReviewError:
        return JsonResponse({"error": "CannotReviewOwnRevision"}, status=403)
    except RevisionAlreadyDecidedError as exc:
        return JsonResponse({"error": "RevisionAlreadyDecided", "status": exc.status}, status=409)
    except OutdatedRevisionError as exc:
        return JsonResponse(
            {"error": "OutdatedRevision", "current_version": exc.current_version}, status=409
        )
    except Exception as exc:
        logger.exception("Failed to record revision decision")
        return JsonResponse({"error": type(exc).__name__}, status=500)

    audit_service.log_event(
        request,
        AuditAction.UPDATE,
        ENTITY_REVISION,
        revision.pk,
        {
            "event": f"REVISION_{revision.status}",
            "document_id": revision.document_id,
            "document_code": revision.document.code,
            "version": revision.version,
            "justification": revision.auditor_comment,
            "superseded_revision_id": superseded.pk if superseded else None,
        },
    )
    return JsonResponse(serialize_revision_decision(revision, superseded))
