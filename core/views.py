import logging
import uuid
from pathlib import Path

from django.db import connection
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
 
from core.mongo import get_mongo_client, get_mongo_db
from core.validators import format_file_size, sniff_file_type
 
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

@csrf_exempt
@require_POST
def upload_document(request):
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return JsonResponse(
            {"error": "Nenhum arquivo enviado. Envie o arquivo no campo 'file'."},
            status=400,
        )
 
    if uploaded_file.size > settings.MAX_UPLOAD_SIZE_BYTES:
        return JsonResponse(
            {
                "error": "Arquivo excede o tamanho máximo permitido (100MB).",
                "max_size_bytes": settings.MAX_UPLOAD_SIZE_BYTES,
            },
            status=413,
        )
 
    file_type = sniff_file_type(uploaded_file)
    if file_type is None:
        return JsonResponse(
            {
                "error": (
                    "Tipo de arquivo não permitido ou conteúdo não corresponde "
                    "a um tipo suportado."
                ),
                "allowed_types": ["pdf", "doc", "jpeg", "png"],
            },
            status=400,
        )
 
    temp_file_id = str(uuid.uuid4())
    temp_dir = Path(settings.TEMP_UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    stored_path = temp_dir / f"{temp_file_id}.{file_type.extension}"
 
    try:
        with open(stored_path, "wb") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
    except OSError:
        logger.exception("Failed to persist uploaded file to temp storage")
        return JsonResponse(
            {"error": "Falha ao salvar o arquivo. Tente novamente."}, status=500
        )
 
    metadata = {
        "temp_file_id": temp_file_id,
        "original_name": uploaded_file.name,
        "stored_path": str(stored_path),
        "file_size_bytes": uploaded_file.size,
        "inferred_type": file_type.mime_type,
        "extension": file_type.extension,
    }
 
    try:
        get_mongo_db()["temp_uploads"].insert_one(dict(metadata))
    except Exception:
        logger.exception("Failed to persist temp upload metadata to MongoDB")
 
    return JsonResponse(
        {
            "temp_file_id": temp_file_id,
            "original_name": uploaded_file.name,
            "file_size": format_file_size(uploaded_file.size),
            "inferred_type": file_type.mime_type,
        },
        status=201,
    )
