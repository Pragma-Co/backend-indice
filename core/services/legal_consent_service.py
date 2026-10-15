from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import (
    LegalClause,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentVersion,
    UserClauseConsent,
    UserLegalAcceptance,
)
from core.services.legal_consent_exceptions import (
    LegalAcceptanceAlreadyRevokedError,
    LegalAcceptanceNotFoundError,
    LegalConsentValidationError,
    LegalDocumentNotFoundError,
    LegalVersionAlreadyAcceptedError,
    LegalVersionNotFoundError,
    OutdatedLegalVersionError,
)

MAX_CONSENTS = 200
USER_AGENT_MAX_LENGTH = UserLegalAcceptance._meta.get_field("user_agent").max_length


def _error(code, message, **extra):
    return {"code": code, "message": message, **extra}


def _is_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


READABLE_STATUSES = (LegalDocumentStatus.PUBLISHED, LegalDocumentStatus.RETIRED)


def _published_versions():
    return LegalDocumentVersion.objects.filter(status=LegalDocumentStatus.PUBLISHED)


def _with_clauses(queryset):
    return queryset.select_related("document").prefetch_related(
        Prefetch("clauses", queryset=LegalClause.objects.order_by("position"))
    )


def current_legal_version(slug) -> LegalDocumentVersion:
    version = (
        _with_clauses(_published_versions().filter(document__slug=slug))
        .order_by("-version")
        .first()
    )
    if version is None:
        raise LegalDocumentNotFoundError()
    return version


def legal_version(version_id) -> LegalDocumentVersion:
    version = _with_clauses(
        LegalDocumentVersion.objects.filter(pk=version_id, status__in=READABLE_STATUSES)
    ).first()
    if version is None:
        raise LegalVersionNotFoundError()
    return version


def legal_documents() -> list[tuple[LegalDocument, LegalDocumentVersion]]:
    current_versions = {}
    for version in _with_clauses(_published_versions()).order_by("document_id", "-version"):
        current_versions.setdefault(version.document_id, version)
    return sorted(
        ((version.document, version) for version in current_versions.values()),
        key=lambda item: (item[0].title, item[0].slug),
    )


def user_acceptances(user):
    return (
        UserLegalAcceptance.objects.filter(user=user)
        .select_related("version__document")
        .prefetch_related(
            Prefetch(
                "clause_consents",
                queryset=UserClauseConsent.objects.select_related("clause").order_by(
                    "clause__position"
                ),
            )
        )
        .order_by("-accepted_at", "-id")
    )


def _consent_item_error(item, decisions):
    if not isinstance(item, dict):
        return _error("invalid", "Each consent must be an object.")
    clause_id = item.get("clause_id")
    if clause_id is None:
        return _error("required", "clause_id is required.")
    if not _is_positive_int(clause_id):
        return _error("invalid", "clause_id must be a positive integer.")
    if not isinstance(item.get("accepted"), bool):
        return _error("invalid", "accepted must be a boolean.")
    if clause_id in decisions:
        return _error("duplicate", "Each clause must be answered only once.")
    return None


def validate_acceptance_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise LegalConsentValidationError(
            {"body": _error("invalid", "Request body must be a JSON object.")}
        )

    errors = {}
    version_id = payload.get("version_id")
    if version_id is None:
        errors["version_id"] = _error("required", "version_id is required.")
    elif not _is_positive_int(version_id):
        errors["version_id"] = _error("invalid", "version_id must be a positive integer.")

    consents = payload.get("consents")
    decisions = {}
    if consents is None:
        errors["consents"] = _error("required", "consents is required.")
    elif not isinstance(consents, list):
        errors["consents"] = _error("invalid", "consents must be a list.")
    elif len(consents) > MAX_CONSENTS:
        errors["consents"] = _error("too_long", f"consents must have at most {MAX_CONSENTS} items.")
    else:
        for index, item in enumerate(consents):
            item_error = _consent_item_error(item, decisions)
            if item_error is not None:
                errors[f"consents[{index}]"] = item_error
            else:
                decisions[item["clause_id"]] = item["accepted"]

    if errors:
        raise LegalConsentValidationError(errors)
    return {"version_id": version_id, "decisions": decisions}


def _validate_decisions_against_clauses(clauses, decisions):
    unknown = sorted(set(decisions) - set(clauses))
    if unknown:
        raise LegalConsentValidationError(
            {
                "consents": _error(
                    "unknown_clauses",
                    "Some clauses do not belong to this version.",
                    clause_ids=unknown,
                )
            }
        )
    missing = sorted(set(clauses) - set(decisions))
    if missing:
        raise LegalConsentValidationError(
            {
                "consents": _error(
                    "missing_clauses",
                    "Every clause of the version must be answered.",
                    clause_ids=missing,
                )
            }
        )
    declined_required = sorted(
        clause_id
        for clause_id, clause in clauses.items()
        if clause.is_required and not decisions[clause_id]
    )
    if declined_required:
        raise LegalConsentValidationError(
            {
                "consents": _error(
                    "required_clause_declined",
                    "Required clauses must be accepted.",
                    clause_ids=declined_required,
                )
            }
        )


def record_acceptance(user, payload, *, ip_address=None, user_agent="") -> UserLegalAcceptance:
    cleaned = validate_acceptance_payload(payload)
    decisions = cleaned["decisions"]

    with transaction.atomic():
        version = (
            _published_versions()
            .select_for_update(no_key=True)
            .filter(pk=cleaned["version_id"])
            .first()
        )
        if version is None:
            raise LegalVersionNotFoundError()
        if UserLegalAcceptance.objects.filter(
            user=user, version=version, revoked_at__isnull=True
        ).exists():
            raise LegalVersionAlreadyAcceptedError()
        current_version_id = (
            _published_versions()
            .filter(document_id=version.document_id)
            .order_by("-version")
            .values_list("pk", flat=True)
            .first()
        )
        if current_version_id != version.pk:
            raise OutdatedLegalVersionError(current_version_id)

        clauses = {clause.pk: clause for clause in version.clauses.all()}
        _validate_decisions_against_clauses(clauses, decisions)

        try:
            with transaction.atomic():
                acceptance = UserLegalAcceptance.objects.create(
                    user=user,
                    version=version,
                    ip_address=ip_address,
                    user_agent=(user_agent or "")[:USER_AGENT_MAX_LENGTH],
                )
        except IntegrityError as exc:
            raise LegalVersionAlreadyAcceptedError() from exc

        UserClauseConsent.objects.bulk_create(
            UserClauseConsent(acceptance=acceptance, clause_id=clause_id, accepted=accepted)
            for clause_id, accepted in decisions.items()
        )
        user.terms_accepted_at = acceptance.accepted_at
        user.save(update_fields=["terms_accepted_at"])

    return user_acceptances(user).get(pk=acceptance.pk)


def revoke_acceptance(user, acceptance_id) -> UserLegalAcceptance:
    with transaction.atomic():
        acceptance = (
            UserLegalAcceptance.objects.select_for_update()
            .filter(pk=acceptance_id, user=user)
            .first()
        )
        if acceptance is None:
            raise LegalAcceptanceNotFoundError()
        if acceptance.revoked_at is not None:
            raise LegalAcceptanceAlreadyRevokedError()

        acceptance.revoked_at = timezone.now()
        acceptance.save(update_fields=["revoked_at"])
        user.terms_accepted_at = (
            UserLegalAcceptance.objects.filter(user=user, revoked_at__isnull=True)
            .order_by("-accepted_at")
            .values_list("accepted_at", flat=True)
            .first()
        )
        user.save(update_fields=["terms_accepted_at"])

    return user_acceptances(user).get(pk=acceptance.pk)
