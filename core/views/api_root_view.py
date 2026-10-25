from django.http import JsonResponse


def api_root(request):
    return JsonResponse(
        {
            "project": "API-6",
            "message": "Backend is running.",
            "endpoints": {
                "health": "/health/",
                "projects": "/projects/",
                "disciplines": "/disciplines/",
                "areas": "/areas/",
                "admin": "/admin/",
            },
        }
    )
