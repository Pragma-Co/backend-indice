import logging

from django.db import connection
from django.http import JsonResponse

from core.mongo import get_mongo_client

logger = logging.getLogger(__name__)


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


def health_check(request):
    """Check connectivity with PostgreSQL and MongoDB.

    Returns HTTP 200 when both databases answer, HTTP 503 otherwise.
    """
    report = {"project": "API-6", "status": "ok", "databases": {}}

    # PostgreSQL (relational) — uses the default Django connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
        report["databases"]["postgresql"] = {
            "connected": True,
            "version": version.split(" on ")[0],
        }
    except Exception as exc:
        # Full details go to the server log only; connection error strings can
        # contain usernames and internal addresses (LGPD)
        logger.exception("PostgreSQL health check failed")
        report["status"] = "degraded"
        report["databases"]["postgresql"] = {
            "connected": False,
            "error": type(exc).__name__,
        }

    # MongoDB (non-relational) — uses the shared pymongo client
    try:
        info = get_mongo_client().server_info()
        report["databases"]["mongodb"] = {
            "connected": True,
            "version": info.get("version"),
        }
    except Exception as exc:
        logger.exception("MongoDB health check failed")
        report["status"] = "degraded"
        report["databases"]["mongodb"] = {
            "connected": False,
            "error": type(exc).__name__,
        }

    status_code = 200 if report["status"] == "ok" else 503
    return JsonResponse(report, status=status_code)
