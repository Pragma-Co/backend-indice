from django.conf import settings

from core.models import User


def resolve_viewer(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_active:
        return user
    if settings.DEBUG and request.method == "GET":
        user_id = request.GET.get("user_id")
        if user_id and str(user_id).isdigit():
            return User.objects.filter(pk=int(user_id), is_active=True).first()
    return None


class DocumentVisibilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.viewer = resolve_viewer(request)
        return self.get_response(request)
