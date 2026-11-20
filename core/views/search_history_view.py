import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core.services.search_history_service import (
    SearchHistoryTermError,
    clear_search_history,
    list_search_history,
    remove_search_term,
)
from core.views.user_view import _active_user, _unauthorized

logger = logging.getLogger(__name__)

TERM_REQUIRED_ERROR = {"term": {"code": "required", "message": "term must not be blank."}}


@require_http_methods(["GET", "DELETE"])
def search_history_view(request):
    user = _active_user(request)
    if user is None:
        return _unauthorized()

    if request.method == "GET":
        return JsonResponse({"results": list_search_history(user)})

    try:
        if "term" in request.GET:
            remove_search_term(user, request.GET["term"])
        else:
            clear_search_history(user)
    except SearchHistoryTermError:
        return JsonResponse({"errors": TERM_REQUIRED_ERROR}, status=400)
    except Exception as exc:
        logger.exception("Failed to delete search history")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return HttpResponse(status=204)
