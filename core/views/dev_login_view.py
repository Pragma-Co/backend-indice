import json

from django.conf import settings
from django.contrib.auth import login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from core.models import User
from core.serializers.user_serializer import serialize_user


@csrf_exempt
@ensure_csrf_cookie
@require_POST
def dev_login_view(request):
    """Provisional sign in used while the real authentication does not exist.

    Opens a session for any active user by id, so it only answers when DEBUG is on.
    """
    if not settings.DEBUG:
        return JsonResponse({"error": "NotFound"}, status=404)

    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    user_id = payload.get("user_id") if isinstance(payload, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        return JsonResponse({"error": "MissingUser"}, status=400)

    user = User.objects.select_related("area").filter(pk=user_id, is_active=True).first()
    if user is None:
        return JsonResponse({"error": "UserNotFound"}, status=404)

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return JsonResponse(serialize_user(user))
