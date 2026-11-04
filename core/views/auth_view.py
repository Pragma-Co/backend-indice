import json

from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from core.serializers.user_serializer import serialize_user
from core.services.auth_exceptions import InvalidCredentialsError
from core.services.auth_service import sign_in


def _credential_errors(payload):
    errors = {}
    email = payload.get("email")
    if not isinstance(email, str) or not email.strip():
        errors["email"] = "Email is required."
    else:
        try:
            validate_email(email.strip())
        except ValidationError:
            errors["email"] = "Enter a valid email address."
    password = payload.get("password")
    if not isinstance(password, str) or not password:
        errors["password"] = "Password is required."
    return errors


@require_GET
@ensure_csrf_cookie
def csrf_view(request):
    return HttpResponse(status=204)


@require_POST
def login_view(request):
    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    errors = _credential_errors(payload)
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        user = sign_in(request, payload["email"], payload["password"])
    except InvalidCredentialsError:
        return JsonResponse({"error": "InvalidCredentials"}, status=401)
    return JsonResponse(serialize_user(user))


@require_POST
def logout_view(request):
    logout(request)
    return HttpResponse(status=204)
