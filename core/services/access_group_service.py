from django.db.models import Q
from django.utils import timezone

from core.models import AccessGroup, DocumentAccess, DocumentAccessGroup, SecrecyLevel
from core.models.choices import AccessStatus, VisibilityScope


def secrecy_level_of(document):
    return SecrecyLevel.objects.get(code=document.confidentiality_level)


def shares_area(document, user):
    return document.areas.filter(pk=user.area_id).exists()


def has_approved_access(document, user):
    return (
        DocumentAccess.objects.filter(document=document, user=user, status=AccessStatus.APPROVED)
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate()))
        .exists()
    )


def matching_groups(document, user, level):
    return AccessGroup.objects.filter(
        active=True,
        memberships__user=user,
        secrecy_level__rank__gte=level.rank,
    ).filter(Q(area__in=document.areas.all()) | Q(project_id=document.project_id))


def has_explicit_group_grant(document, user):
    return DocumentAccessGroup.objects.filter(
        document=document, group__active=True, group__memberships__user=user
    ).exists()


def can_user_view_document(document, user):
    if user is None or not user.is_active:
        return False
    if document.responsible_id == user.id:
        return True
    level = secrecy_level_of(document)
    if level.visibility == VisibilityScope.EVERYONE:
        return True
    if level.visibility == VisibilityScope.AREA and shares_area(document, user):
        return True
    return (
        has_approved_access(document, user)
        or matching_groups(document, user, level).exists()
        or has_explicit_group_grant(document, user)
    )
