from django.http import JsonResponse
from django.urls import Resolver404, resolve

PUBLIC_URL_NAMES = frozenset(
    {
        "api-root",
        "health-check",
        "auth-csrf",
        "auth-login",
        "auth-logout",
        "legal-document-list",
        "legal-version-detail",
        "legal-document-current",
    }
)
PUBLIC_NAMESPACES = frozenset({"admin"})


class LoginRequiredJsonMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_public(request) or self._is_signed_in(request):
            return self.get_response(request)
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)

    @staticmethod
    def _is_public(request):
        if request.method == "OPTIONS":
            return True
        try:
            match = resolve(request.path_info, getattr(request, "urlconf", None))
        except Resolver404:
            return True
        return match.url_name in PUBLIC_URL_NAMES or bool(
            PUBLIC_NAMESPACES.intersection(match.namespaces)
        )

    @staticmethod
    def _is_signed_in(request):
        user = request.user
        return user.is_authenticated and user.is_active
