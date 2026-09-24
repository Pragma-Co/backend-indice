"""Inline file streaming for document preview."""

import logging
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET
from django.views.decorators.clickjacking import xframe_options_exempt

from core.services.documents_exceptions import DocumentFilePermissionError
from core.services.file_service import (
    DocumentFileNotFoundError,
    get_document_file_for_view,
)

logger = logging.getLogger(__name__)


@require_GET
@xframe_options_exempt
def document_file_view(request, file_id):
    user_id = request.GET.get("user_id")

    try:
        file_obj = get_document_file_for_view(file_id, user_id)
    except DocumentFileNotFoundError:
        raise Http404("Arquivo não encontrado.")
    except DocumentFilePermissionError:
        raise Http404("Arquivo não encontrado.")
    except Exception as exc:
        logger.exception("Failed to stream document file")
        raise Http404(type(exc).__name__)

    storage_path = Path(settings.DOCUMENT_STORAGE_DIR) / file_obj.storage_path
    if not storage_path.is_file():
        logger.warning("File missing in storage: %s", storage_path)
        raise Http404("Arquivo não encontrado no storage.")

    content_type = (
        file_obj.mime_type
        or mimetypes.guess_type(file_obj.original_name)[0]
        or "application/octet-stream"
    )

    stream = storage_path.open("rb")
    response = FileResponse(stream, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{file_obj.original_name}"'
    response["Cache-Control"] = "private, no-store"
    return response
