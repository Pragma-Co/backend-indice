from django.http import JsonResponse

def api_root(request):
    """Simple welcome endpoint listing the available routes."""
    return JsonResponse(
        {
            "project": "API-6",
            "message": "Backend is running.",
            "endpoints": {
                "health": "/health/",
                "admin": "/admin/",
            },
        }
    )

