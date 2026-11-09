import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core.serializers.notification_serializer import (
    serialize_notification,
    serialize_notification_page,
)
from core.services.notification_exceptions import (
    NotificationNotFoundError,
    NotificationValidationError,
)
from core.services.notification_service import (
    list_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)
from core.views.user_view import _active_user, _unauthorized

logger = logging.getLogger(__name__)


@require_GET
def notifications_view(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()
    try:
        return JsonResponse(serialize_notification_page(list_notifications(user, request.GET)))
    except NotificationValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list notifications")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_http_methods(["PATCH"])
def notification_read_view(request, notification_id):
    user = _active_user(request)
    if user is None:
        return _unauthorized()
    try:
        notification = mark_notification_as_read(user, notification_id)
    except NotificationNotFoundError:
        return JsonResponse({"error": "NotificationNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to mark notification as read")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse(serialize_notification(notification))


@require_http_methods(["PATCH"])
def notifications_read_all_view(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()
    try:
        updated = mark_all_notifications_as_read(user)
    except Exception as exc:
        logger.exception("Failed to mark all notifications as read")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse({"updated": updated, "unread_count": 0})
