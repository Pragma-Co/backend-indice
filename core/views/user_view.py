import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.models import AuditAction
from core.serializers.user_serializer import (
    UserPayloadValidationError,
    serialize_user,
    validate_user_update,
)
from core.services import audit_service
from core.services.excluded_identifier_service import (
    ExcludedIdentifierError,
    store_excluded_identifier,
)


def _unauthorized():
    return JsonResponse({"error": "Authentication required."}, status=401)


def _active_user(request):
    user = request.user
    return user if user.is_authenticated and user.is_active else None


@require_http_methods(["GET", "PUT"])
def user_me(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    if request.method == "GET":
        return JsonResponse(serialize_user(user))

    if request.method == "PUT":
        try:
            payload = json.loads(request.body or b"")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

        try:
            updates = validate_user_update(payload, user)
        except UserPayloadValidationError as exc:
            return JsonResponse({"errors": exc.errors}, status=400)

        try:
            with transaction.atomic():
                user.name = updates["name"]
                user.email = updates["email"]
                user.save(update_fields=["name", "email"])
        except IntegrityError:
            return JsonResponse(
                {"errors": {"email": "A user with this email address already exists."}},
                status=400,
            )
        except ExcludedIdentifierError as exc:
            return JsonResponse({"errors": {"email": str(exc)}}, status=400)

        audit_service.log_event(
            request,
            AuditAction.UPDATE,
            "app_user",
            user.pk,
            {"event": "PERSONAL_DATA_UPDATED", "fields": ["name", "email"]},
        )
        return JsonResponse(serialize_user(user))


@require_http_methods(["POST"])
def request_user_deletion(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    requested_at = timezone.now()
    with transaction.atomic():
        store_excluded_identifier(user.email)
        user.is_active = False
        user.deletion_requested_at = requested_at
        user.save(update_fields=["is_active", "deletion_requested_at"])
        audit_service.log_event(
            request,
            AuditAction.UPDATE,
            "app_user",
            user.pk,
            {"event": "PERSONAL_DATA_DELETION_REQUESTED"},
        )
    return JsonResponse(
        {
            "message": "Personal data deletion request received.",
            "deletion_requested_at": requested_at.isoformat(),
        },
        status=202,
    )
