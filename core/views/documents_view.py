from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services.documents_service import get_documents, get_simple_filters


@require_GET
def documents(request):
    return JsonResponse({"documents": get_documents(request.GET)})


@require_GET
def simple_filters(request):
    return JsonResponse(get_simple_filters())
