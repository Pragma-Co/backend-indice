def serialize_group(group):
    return {
        "id": group.pk,
        "name": group.name,
        "description": group.description,
        "scope": group.scope,
        "area_id": group.area_id,
        "secrecy_level": group.secrecy_level_id,
        "active": group.active,
        "created_by": group.created_by_id,
        "created_at": group.created_at.isoformat(),
    }


def serialize_member(membership):
    return {
        "user_id": membership.user_id,
        "name": membership.user.name,
        "email": membership.user.email,
        "added_by": membership.added_by_id,
        "added_at": membership.added_at.isoformat(),
    }
