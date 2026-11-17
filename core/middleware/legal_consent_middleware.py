from django.http import JsonResponse
from django.urls import Resolver404, resolve

from core.middleware.login_required_middleware import PUBLIC_NAMESPACES, PUBLIC_URL_NAMES
from core.services.legal_consent_service import has_pending_legal_terms

EXEMPT_URL_NAMES = PUBLIC_URL_NAMES | frozenset(
    {
        "user-me",
        "user-legal-pending",
        "user-legal-acceptances",
        "user-legal-acceptance-revoke",
        "user-deletion-request",
    }
)


class LegalConsentRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_exempt(request) or not self._is_signed_in(request):
            return self.get_response(request)
        if has_pending_legal_terms(request.user):
            return JsonResponse({"error": "LegalAcceptanceRequired"}, status=403)
        return self.get_response(request)

    @staticmethod
    def _is_exempt(request):
        if request.method == "OPTIONS":
            return True
        try:
            match = resolve(request.path_info, getattr(request, "urlconf", None))
        except Resolver404:
            return True
        return match.url_name in EXEMPT_URL_NAMES or bool(
            PUBLIC_NAMESPACES.intersection(match.namespaces)
        )

    @staticmethod
    def _is_signed_in(request):
        user = request.user
        return user.is_authenticated and user.is_active
