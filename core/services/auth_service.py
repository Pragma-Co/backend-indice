from django.contrib.auth import authenticate, login

from core.models import AuditAction
from core.services import audit_service
from core.services.auth_exceptions import InvalidCredentialsError

ENTITY_USER = "app_user"


def sign_in(request, email, password):
    user = authenticate(request, email=email.strip(), password=password)
    if user is None:
        raise InvalidCredentialsError
    login(request, user)
    audit_service.log_event(
        request,
        AuditAction.LOGIN,
        ENTITY_USER,
        user.pk,
        {"user_agent": audit_service.client_user_agent(request)},
    )
    return user
