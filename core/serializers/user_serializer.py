from django.core.exceptions import ValidationError
from django.forms import EmailField

from core.models import User
from core.services.excluded_identifier_service import is_identifier_excluded


class UserPayloadValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("User payload is invalid.")


def _isoformat(value):
    return value.isoformat() if value is not None else None


def serialize_user(user):
    return {
        "id": user.pk,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "area": {
            "id": user.area_id,
            "acronym": user.area.acronym,
            "name": user.area.name,
        },
        "terms_accepted_at": _isoformat(user.terms_accepted_at),
        "is_active": user.is_active,
        "created_at": _isoformat(user.created_at),
        "deletion_requested_at": _isoformat(user.deletion_requested_at),
    }


def validate_user_update(payload, user):
    if not isinstance(payload, dict):
        raise UserPayloadValidationError({"body": "Expected a JSON object."})

    allowed_fields = {"name", "email"}
    errors = {}
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        errors["unknown_fields"] = unknown_fields

    for field in allowed_fields:
        if field not in payload:
            errors[field] = "This field is required."

    name = payload.get("name")
    if "name" in payload:
        if not isinstance(name, str) or not name.strip():
            errors["name"] = "Enter a non-empty name."
        elif len(name.strip()) > 150:
            errors["name"] = "Ensure this field has no more than 150 characters."

    email = payload.get("email")
    if "email" in payload:
        try:
            email = EmailField(max_length=254).clean(email)
        except ValidationError:
            errors["email"] = "Enter a valid email address."
        else:
            email = User.objects.normalize_email(email)
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                errors["email"] = "A user with this email address already exists."
            elif is_identifier_excluded(email):
                errors["email"] = "This email address cannot be used for an account."

    if errors:
        raise UserPayloadValidationError(errors)

    return {"name": name.strip(), "email": email}
