from django.db.models import Exists, OuterRef, Q, Subquery

from core.models import (
    AccessGroup,
    Document,
    DocumentAccess,
    DocumentAccessGroup,
    DocumentArea,
    SecrecyLevel,
)
from core.models.choices import VisibilityScope
from core.services.access_request_service import active_grant_filter


def levels_with(visibility):
    return SecrecyLevel.objects.filter(visibility=visibility).values("code")


def document_rank():
    return SecrecyLevel.objects.filter(code=OuterRef(OuterRef("confidentiality_level"))).values(
        "rank"
    )[:1]


def active_grant(user):
    return Exists(
        DocumentAccess.objects.filter(active_grant_filter(), document=OuterRef("pk"), user=user)
    )


def area_membership(user):
    return Exists(DocumentArea.objects.filter(document=OuterRef("pk"), area_id=user.area_id))


def group_grant(user):
    area_match = DocumentArea.objects.filter(
        document=OuterRef(OuterRef("pk")), area=OuterRef("area")
    )
    return Exists(
        AccessGroup.objects.filter(active=True, memberships__user=user)
        .filter(secrecy_level__rank__gte=Subquery(document_rank()))
        .filter(Q(project=OuterRef("project")) | Q(Exists(area_match)))
    )


def explicit_group_grant(user):
    return Exists(
        DocumentAccessGroup.objects.filter(
            document=OuterRef("pk"), group__active=True, group__memberships__user=user
        )
    )


def visibility_criteria(user):
    return (
        Q(responsible=user)
        | Q(active_grant(user))
        | Q(confidentiality_level__in=levels_with(VisibilityScope.EVERYONE))
        | (
            Q(confidentiality_level__in=levels_with(VisibilityScope.AREA))
            & Q(area_membership(user))
        )
        | Q(group_grant(user))
        | Q(explicit_group_grant(user))
    )


def visible_documents(queryset, user):
    if user is None or not user.is_active:
        return queryset.none()
    return queryset.filter(visibility_criteria(user))


def is_visible(document, user):
    return visible_documents(Document.objects.filter(pk=document.pk), user).exists()
