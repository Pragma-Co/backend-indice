from django.db import transaction

from core.models import DocumentAccess
from core.services.excluded_identifier_service import store_excluded_identifier

ANONYMOUS_NAME = "Usuário removido"
ANONYMOUS_EMAIL_DOMAIN = "anonymized.invalid"

ANONYMIZED_FIELDS = (
    "name",
    "email",
    "password",
    "terms_accepted_at",
    "is_active",
    "deletion_requested_at",
)


def anonymized_email(user_id):
    return f"anonymized-{user_id}@{ANONYMOUS_EMAIL_DOMAIN}"


def anonymize_user(user, *, requested_at):
    with transaction.atomic():
        store_excluded_identifier(user.email)

        user.name = ANONYMOUS_NAME
        user.email = anonymized_email(user.pk)
        user.set_unusable_password()
        user.terms_accepted_at = None
        user.is_active = False
        user.deletion_requested_at = requested_at
        user.save(update_fields=list(ANONYMIZED_FIELDS))

        cleared = DocumentAccess.objects.filter(user=user).update(justification="")
    return {
        "anonymized": True,
        "fields": list(ANONYMIZED_FIELDS),
        "cleared": {"document_access.justification": cleared},
    }


def is_anonymized(user):
    return user.email == anonymized_email(user.pk)


__all__ = [
    "ANONYMIZED_FIELDS",
    "ANONYMOUS_NAME",
    "anonymize_user",
    "anonymized_email",
    "is_anonymized"
]
