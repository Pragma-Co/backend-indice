from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services.search_history_service import list_search_history
from core.views.user_view import _active_user, _unauthorized


@require_GET
def search_history_view(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()
    return JsonResponse({"results": list_search_history(user)})
