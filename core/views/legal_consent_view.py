import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import AuditAction
from core.serializers.legal_consent_serializer import (
    serialize_acceptance,
    serialize_acceptance_history,
    serialize_legal_documents,
    serialize_legal_version,
)
from core.services import audit_service
from core.services.legal_consent_exceptions import (
    LegalAcceptanceAlreadyRevokedError,
    LegalAcceptanceNotFoundError,
    LegalConsentValidationError,
    LegalDocumentNotFoundError,
    LegalVersionAlreadyAcceptedError,
    LegalVersionNotFoundError,
    OutdatedLegalVersionError,
)
from core.services.legal_consent_service import (
    current_legal_version,
    legal_documents,
    legal_version,
    record_acceptance,
    revoke_acceptance,
    user_acceptances,
)

logger = logging.getLogger(__name__)

ENTITY_LEGAL_ACCEPTANCE = "user_legal_acceptance"


@require_GET
def current_legal_version_view(request, slug):
    try:
        version = current_legal_version(slug)
        return JsonResponse(serialize_legal_version(version))
    except LegalDocumentNotFoundError:
        return JsonResponse({"error": "LegalDocumentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to load the current legal version")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_GET
def legal_version_view(request, version_id):
    try:
        return JsonResponse(serialize_legal_version(legal_version(version_id)))
    except LegalVersionNotFoundError:
        return JsonResponse({"error": "LegalVersionNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to load the legal version")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_GET
def legal_documents_view(request):
    try:
        return JsonResponse(serialize_legal_documents(legal_documents()))
    except Exception as exc:
        logger.exception("Failed to list the legal documents")
        return JsonResponse({"error": type(exc).__name__}, status=500)


@require_http_methods(["GET", "POST"])
def legal_acceptances_view(request):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if request.method == "POST":
        return _create_acceptance(request, user)
    try:
        return JsonResponse(serialize_acceptance_history(user_acceptances(user)))
    except Exception as exc:
        logger.exception("Failed to list legal acceptances")
        return JsonResponse({"error": type(exc).__name__}, status=500)


def _create_acceptance(request, user):
    try:
        payload = json.loads(request.body or b"")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "InvalidJSON"}, status=400)

    try:
        with transaction.atomic():
            acceptance = record_acceptance(
                user,
                payload,
                ip_address=audit_service.client_ip(request),
                user_agent=audit_service.client_user_agent(request),
            )
            audit_service.log_event_required(
                request,
                AuditAction.CREATE,
                ENTITY_LEGAL_ACCEPTANCE,
                acceptance.pk,
                {
                    "event": "LEGAL_TERMS_ACCEPTED",
                    "document": acceptance.version.document.slug,
                    "version": acceptance.version.version,
                    "declined_clauses": [
                        consent.clause.code
                        for consent in acceptance.clause_consents.all()
                        if not consent.accepted
                    ],
                },
            )
    except LegalConsentValidationError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except LegalVersionNotFoundError:
        return JsonResponse({"error": "LegalVersionNotFound"}, status=404)
    except LegalVersionAlreadyAcceptedError:
        return JsonResponse({"error": "LegalVersionAlreadyAccepted"}, status=409)
    except OutdatedLegalVersionError as exc:
        return JsonResponse(
            {"error": "OutdatedLegalVersion", "current_version_id": exc.current_version_id},
            status=409,
        )
    except audit_service.AuditLogWriteError:
        return JsonResponse({"error": "AuditUnavailable"}, status=503)
    except Exception as exc:
        logger.exception("Failed to record legal acceptance")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse(serialize_acceptance(acceptance), status=201)


@require_POST
def revoke_legal_acceptance_view(request, acceptance_id):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)
    try:
        with transaction.atomic():
            acceptance = revoke_acceptance(user, acceptance_id)
            audit_service.log_event_required(
                request,
                AuditAction.UPDATE,
                ENTITY_LEGAL_ACCEPTANCE,
                acceptance.pk,
                {
                    "event": "LEGAL_TERMS_REVOKED",
                    "document": acceptance.version.document.slug,
                    "version": acceptance.version.version,
                },
            )
    except LegalAcceptanceNotFoundError:
        return JsonResponse({"error": "LegalAcceptanceNotFound"}, status=404)
    except LegalAcceptanceAlreadyRevokedError:
        return JsonResponse({"error": "LegalAcceptanceAlreadyRevoked"}, status=409)
    except audit_service.AuditLogWriteError:
        return JsonResponse({"error": "AuditUnavailable"}, status=503)
    except Exception as exc:
        logger.exception("Failed to revoke legal acceptance")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    return JsonResponse(serialize_acceptance(acceptance))
