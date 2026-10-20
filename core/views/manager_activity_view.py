import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services.manager_activity_exceptions import ActivityQueryError
from core.services.manager_activity_service import list_activities
from core.services.revision_review_service import is_revision_reviewer

logger = logging.getLogger(__name__)


@require_GET
def manager_activities_view(request):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if not is_revision_reviewer(user):
        return JsonResponse({"error": "PermissionDenied"}, status=403)
    try:
        return JsonResponse(list_activities(user, request.GET))
    except ActivityQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list manager activities")
        return JsonResponse({"error": type(exc).__name__}, status=500)
