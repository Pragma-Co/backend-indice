from django.utils import timezone

from core.models import (
    AccessGroup,
    AccessStatus,
    AccessType,
    DocumentAccess,
    DocumentAccessGroup,
    SecrecyLevel,
    User,
)
from core.models.choices import VisibilityScope

REQUIRED = "required"
INVALID = "invalid"
NOT_FOUND = "not_found"
NOT_ALLOWED = "not_allowed"
INSUFFICIENT_LEVEL = "insufficient_level"

GROUPS_FIELD = "authorized_group_ids"
USERS_FIELD = "authorized_user_ids"


def _error(code, message):
    return {"code": code, "message": message}


def _clean_id_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    ids = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            return None
        if item not in ids:
            ids.append(item)
    return ids


def _clean_groups(raw, level, errors):
    group_ids = _clean_id_list(raw)
    if group_ids is None:
        errors[GROUPS_FIELD] = _error(INVALID, "Authorized groups must be a list of group ids.")
        return []
    if not group_ids:
        return []
    if level.visibility != VisibilityScope.AREA:
        errors[GROUPS_FIELD] = _error(
            NOT_ALLOWED, "Authorized groups are only accepted for CONFIDENTIAL documents."
        )
        return []
    groups = list(
        AccessGroup.objects.filter(pk__in=group_ids, active=True).select_related("secrecy_level")
    )
    missing = sorted(set(group_ids) - {group.pk for group in groups})
    if missing:
        errors[GROUPS_FIELD] = _error(NOT_FOUND, f"Unknown or inactive groups: {missing}.")
        return []
    weak = sorted(group.pk for group in groups if group.secrecy_level.rank < level.rank)
    if weak:
        errors[GROUPS_FIELD] = _error(
            INSUFFICIENT_LEVEL,
            f"Groups {weak} have a secrecy level below the document's.",
        )
        return []
    return groups


def _clean_users(raw, level, responsible, errors):
    user_ids = _clean_id_list(raw)
    if user_ids is None:
        errors[USERS_FIELD] = _error(INVALID, "Authorized users must be a list of user ids.")
        return []
    selected_users_level = level.visibility == VisibilityScope.SELECTED_USERS
    if user_ids and not selected_users_level:
        errors[USERS_FIELD] = _error(
            NOT_ALLOWED, "Authorized users are only accepted for SECRET documents."
        )
        return []
    if not selected_users_level:
        return []
    if responsible is not None:
        user_ids = [user_id for user_id in user_ids if user_id != responsible.pk]
    if not user_ids:
        errors[USERS_FIELD] = _error(
            REQUIRED,
            "A SECRET document requires at least one authorized user besides the responsible.",
        )
        return []
    users = list(User.objects.filter(pk__in=user_ids, is_active=True))
    missing = sorted(set(user_ids) - {user.pk for user in users})
    if missing:
        errors[USERS_FIELD] = _error(NOT_FOUND, f"Unknown or inactive users: {missing}.")
        return []
    return users


def clean_access_permissions(payload, confidentiality, responsible, errors) -> dict:
    level = SecrecyLevel.objects.filter(code=confidentiality).first()
    if level is None:
        return {"authorized_groups": [], "authorized_users": []}
    return {
        "authorized_groups": _clean_groups(payload.get(GROUPS_FIELD), level, errors),
        "authorized_users": _clean_users(payload.get(USERS_FIELD), level, responsible, errors),
    }


def grant_access_permissions(document, cleaned, granted_by) -> None:
    DocumentAccessGroup.objects.bulk_create(
        [
            DocumentAccessGroup(document=document, group=group, granted_by=granted_by)
            for group in cleaned["authorized_groups"]
        ]
    )
    now = timezone.now()
    DocumentAccess.objects.bulk_create(
        [
            DocumentAccess(
                document=document,
                user=user,
                status=AccessStatus.APPROVED,
                access_type=AccessType.PERMANENT,
                approver=granted_by,
                decided_at=now,
            )
            for user in cleaned["authorized_users"]
        ]
    )
