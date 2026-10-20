from django.db import transaction

from core.models import (
    AccessStatus,
    Area,
    Document,
    DocumentAccess,
    LegalDocumentVersion,
    Revision,
    RevisionStatus,
    Role,
    User,
    UserLegalAcceptance,
)
from core.services.excluded_identifier_service import store_excluded_identifier

ANONYMOUS_NAME = "Usuário removido"
ANONYMOUS_EMAIL_DOMAIN = "anonymized.invalid"

ANONYMIZED_FIELDS = (
    "name",
    "email",
    "password",
    "terms_accepted_at",
    "is_active",
)


class NoReplacementManagerError(Exception):
    """No other active manager is available to take over the user's records."""


def anonymized_email(user_id):
    return f"anonymized-{user_id}@{ANONYMOUS_EMAIL_DOMAIN}"


def find_replacement_manager(user):
    """Another active manager of the user's area; an active admin is the last resort."""
    candidates = User.objects.filter(is_active=True).exclude(pk=user.pk)
    area = Area.objects.select_related("manager").filter(pk=user.area_id).first()
    if area is not None and area.manager_id and area.manager_id != user.pk:
        manager = candidates.filter(pk=area.manager_id).first()
        if manager is not None:
            return manager
    return (
        candidates.filter(area_id=user.area_id, role=Role.AUDITOR).order_by("pk").first()
        or candidates.filter(role=Role.ADMIN).order_by("pk").first()
    )


def _require_replacement(user):
    replacement = find_replacement_manager(user)
    if replacement is None:
        raise NoReplacementManagerError(
            "No other active manager is available to take over this user's records."
        )
    return replacement


def _reassign_responsibilities(user, replacement):
    """Moves what the user still has to act on; returns counts by relation."""
    pending_reviews = Revision.objects.filter(auditor=user, status=RevisionStatus.PENDING).update(
        auditor=replacement
    )
    documents = Document.objects.filter(responsible=user).update(responsible=replacement)
    areas = Area.objects.filter(manager=user).update(manager=replacement)
    return {
        "revision.auditor(pending)": pending_reviews,
        "document.responsible": documents,
        "area.manager": areas,
    }


def _reassign_history(user, replacement):
    """Hard delete only: every remaining reference must point to someone else."""
    return {
        "document.created_by": Document.objects.filter(created_by=user).update(
            created_by=replacement
        ),
        "document.updated_by": Document.objects.filter(updated_by=user).update(
            updated_by=replacement
        ),
        "document.archived_by": Document.objects.filter(archived_by=user).update(
            archived_by=replacement
        ),
        "revision.author": Revision.objects.filter(author=user).update(author=replacement),
        "revision.auditor": Revision.objects.filter(auditor=user).update(auditor=replacement),
        "document_access.approver": DocumentAccess.objects.filter(approver=user).update(
            approver=replacement
        ),
        "legal_document_version.created_by": LegalDocumentVersion.objects.filter(
            created_by=user
        ).update(created_by=replacement),
    }


def delete_user_account(user):
    """Hard delete, requested by the user. Audit rows keep their actor name in `record`."""
    with transaction.atomic():
        replacement = _require_replacement(user)
        store_excluded_identifier(user.email)

        reassigned = _reassign_responsibilities(user, replacement)
        reassigned.update(_reassign_history(user, replacement))
        UserLegalAcceptance.objects.filter(user=user).delete()
        user.delete()
    return {
        "deleted": True,
        "reassigned_to": replacement.pk,
        "reassigned": reassigned,
    }


def anonymize_user(user):
    """Soft delete for a dismissed user who did not ask for deletion."""
    with transaction.atomic():
        replacement = _require_replacement(user)
        store_excluded_identifier(user.email)

        reassigned = _reassign_responsibilities(user, replacement)
        removed_requests, _ = DocumentAccess.objects.filter(
            user=user, status=AccessStatus.PENDING
        ).delete()
        DocumentAccess.objects.filter(user=user).update(justification="")

        user.name = ANONYMOUS_NAME
        user.email = anonymized_email(user.pk)
        user.set_unusable_password()
        user.terms_accepted_at = None
        user.is_active = False
        user.save(update_fields=list(ANONYMIZED_FIELDS))
    return {
        "anonymized": True,
        "fields": list(ANONYMIZED_FIELDS),
        "reassigned_to": replacement.pk,
        "reassigned": reassigned,
        "removed": {"document_access(pending)": removed_requests},
    }


def is_anonymized(user):
    return user.email == anonymized_email(user.pk)


__all__ = [
    "ANONYMIZED_FIELDS",
    "ANONYMOUS_NAME",
    "NoReplacementManagerError",
    "anonymize_user",
    "anonymized_email",
    "delete_user_account",
    "find_replacement_manager",
    "is_anonymized",
]
