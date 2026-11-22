from django.db import IntegrityError, transaction

from core.models import (
    MANAGER_ROLES,
    AccessGroup,
    AccessGroupMember,
    AccessGroupScope,
    SecrecyLevel,
    User,
)


class GroupManagementError(Exception):
    def __init__(self, code, status=400, errors=None):
        self.code = code
        self.status = status
        self.errors = errors
        super().__init__(code)


def groups_for_manager(manager):
    return AccessGroup.objects.filter(scope=AccessGroupScope.AREA, area_id=manager.area_id)


def area_users_for_manager(manager):
    return (
        User.objects.filter(is_active=True, area_id=manager.area_id)
        .exclude(role__in=MANAGER_ROLES)
        .order_by("name", "id")
    )


def group_members_for_manager(manager, group):
    return (
        group.memberships.select_related("user")
        .filter(user__area_id=manager.area_id)
        .exclude(user__role__in=MANAGER_ROLES)
        .order_by("user__name", "user_id")
    )


def ensure_manageable_user(manager, user):
    if user is None or not user.is_active:
        raise GroupManagementError("UserNotFound", 404)
    if user.pk == manager.pk:
        raise GroupManagementError("CannotManageSelf", 403)
    if user.role in MANAGER_ROLES:
        raise GroupManagementError("CannotManageManager", 403)
    if user.area_id != manager.area_id:
        raise GroupManagementError("UserOutsideArea", 403)
    return user


def get_group(manager, group_id):
    group = groups_for_manager(manager).filter(pk=group_id).first()
    if group is None:
        raise GroupManagementError("AccessGroupNotFound", 404)
    return group


def create_group(manager, payload):
    if not isinstance(payload, dict):
        raise GroupManagementError("InvalidPayload", errors={"body": "Expected a JSON object."})
    errors = {}
    for field in set(payload) - {"name", "description", "secrecy_level"}:
        errors[field] = "Unknown field."
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120 or "\x00" in name:
        errors["name"] = "Must be a non-empty string of at most 120 characters."
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 500 or "\x00" in description:
        errors["description"] = "Must be a string of at most 500 characters."
    level = payload.get("secrecy_level")
    if (
        not isinstance(level, str)
        or "\x00" in level
        or not SecrecyLevel.objects.filter(pk=level).exists()
    ):
        errors["secrecy_level"] = "Must be an existing secrecy level code."
    if errors:
        raise GroupManagementError("InvalidPayload", errors=errors)
    try:
        with transaction.atomic():
            return AccessGroup.objects.create(
                name=name.strip(),
                description=description,
                scope=AccessGroupScope.AREA,
                area_id=manager.area_id,
                secrecy_level_id=level,
                created_by=manager,
            )
    except IntegrityError as exc:
        raise GroupManagementError("AccessGroupConflict", 409) from exc


def add_member(manager, group_id, payload):
    with transaction.atomic():
        group = get_group(manager, group_id)
        if not group.active:
            raise GroupManagementError("AccessGroupInactive", 409)
        if not isinstance(payload, dict) or set(payload) != {"user_id"}:
            raise GroupManagementError("InvalidPayload", errors={"user_id": "Provide a user_id."})
        user_id = payload["user_id"]
        if type(user_id) is not int or user_id < 1:
            raise GroupManagementError(
                "InvalidPayload", errors={"user_id": "Must be a positive integer."}
            )
        user = ensure_manageable_user(manager, User.objects.filter(pk=user_id).first())
        membership, created = AccessGroupMember.objects.get_or_create(
            group=group, user=user, defaults={"added_by": manager}
        )
        if not created:
            raise GroupManagementError("AccessGroupMemberExists", 409)
        return membership


def remove_member(manager, group_id, user_id):
    with transaction.atomic():
        group = get_group(manager, group_id)
        membership = (
            AccessGroupMember.objects.select_related("user")
            .filter(group=group, user_id=user_id)
            .first()
        )
        if membership is None:
            raise GroupManagementError("AccessGroupMemberNotFound", 404)
        ensure_manageable_user(manager, membership.user)
        membership.delete()
