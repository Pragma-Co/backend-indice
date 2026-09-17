from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Prefetch, Q
from django.utils import timezone

from core.models import Area, Document, DocumentAccess, DocumentType, Revision, User
from core.models.choices import AccessStatus, RevisionStatus
from core.services.documents_exceptions import (
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)

SIMPLE_FILTERS_CACHE_KEY = "documents:simple-filters"
SIMPLE_FILTERS_CACHE_TIMEOUT = 300
DATE_FILTERS = [
    {"value": "last_7_days", "label": "Últimos 7 dias"},
    {"value": "last_month", "label": "Último mês"},
    {"value": "last_year", "label": "Último ano"},
]


DATE_RANGES = {
    "last_7_days": timedelta(days=7),
    "last_month": timedelta(days=30),
    "last_year": timedelta(days=365),
}


def build_simple_filters():
    return {
        "areas": list(
            Area.objects.filter(active=True).order_by("acronym").values("acronym", "name")
        ),
        "types": list(
            DocumentType.objects.filter(active=True).order_by("code").values("code", "name")
        ),
        "dates": DATE_FILTERS,
    }


def get_simple_filters():
    payload = cache.get(SIMPLE_FILTERS_CACHE_KEY)
    if payload is None:
        payload = build_simple_filters()
        cache.set(SIMPLE_FILTERS_CACHE_KEY, payload, SIMPLE_FILTERS_CACHE_TIMEOUT)
    return payload


def _apply_date_filter(queryset, date_filter):
    if date_filter not in DATE_RANGES:
        return queryset
    return queryset.filter(created_at__gte=timezone.now() - DATE_RANGES[date_filter])


def _apply_date_range(queryset, date_from, date_to):
    try:
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date.fromisoformat(date_from))
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date.fromisoformat(date_to))
    except ValueError:
        return queryset.none()
    return queryset


def get_documents(params):
    queryset = (
        Document.objects.filter(document_type__active=True)
        .filter(Q(areas__active=True) | Q(areas__isnull=True))
        .select_related("document_type", "discipline", "project")
        .prefetch_related("areas", "tags")
        .order_by("-updated_at", "-id")
        .distinct()
    )

    search_term = params.get("q", "").strip()
    if search_term:
        queryset = queryset.filter(
            Q(title__icontains=search_term)
            | Q(code__icontains=search_term)
            | Q(description__icontains=search_term)
            | Q(tags__name__icontains=search_term)
        ).distinct()

    area = params.get("area", "").strip()
    if area:
        queryset = queryset.filter(areas__active=True, areas__acronym=area).distinct()

    document_type = params.get("tipo", "").strip()
    if document_type:
        queryset = queryset.filter(document_type__active=True, document_type__code=document_type)

    queryset = _apply_date_filter(queryset, params.get("data", "").strip())
    queryset = _apply_date_range(
        queryset,
        params.get("date_from", "").strip(),
        params.get("date_to", "").strip(),
    )

    return [_serialize_document(document) for document in queryset]


def _serialize_document(document):
    return {
        "id": document.id,
        "code": document.code,
        "title": document.title,
        "description": document.description or "",
        "type": {
            "code": document.document_type.code,
            "name": document.document_type.name,
        },
        "areas": [
            {"acronym": area.acronym, "name": area.name}
            for area in document.areas.all()
            if area.active
        ],
        "updated_at": document.updated_at.isoformat(),
    }


ACCESS_APPROVED = "APPROVED"
ACCESS_IN_REVIEW = "IN_REVIEW"
ACCESS_PENDING = "PENDING"


def _get_document_or_none(document_id):
    return (
        Document.objects.filter(document_type__active=True)
        .select_related("project", "discipline", "document_type", "responsible")
        .prefetch_related(
            "areas",
            Prefetch(
                "revisions",
                queryset=Revision.objects.select_related("author").order_by("-version"),
            ),
        )
        .filter(pk=document_id)
        .first()
    )


def _get_current_revision(document):
    revisions = list(document.revisions.all())
    if not revisions:
        return None
    for revision in revisions:
        if revision.status == RevisionStatus.APPROVED:
            return revision
    return revisions[0]


def _compute_access_status(document, user):
    if user is None:
        return ACCESS_PENDING

    if document.responsible_id == user.id:
        return ACCESS_APPROVED

    has_grant = DocumentAccess.objects.filter(
        document=document, user=user, status=AccessStatus.APPROVED
    ).exists()
    if has_grant:
        return ACCESS_APPROVED

    current_revision = _get_current_revision(document)
    if current_revision is None or current_revision.status != RevisionStatus.APPROVED:
        return ACCESS_IN_REVIEW

    return ACCESS_PENDING


def _serialize_revision(revision):
    return {
        "version": revision.version,
        "status": revision.status,
        "issue_date": revision.issue_date.isoformat() if revision.issue_date else None,
        "change_description": revision.change_description,
        "author": {"id": revision.author_id, "name": revision.author.name},
        "created_at": revision.created_at.isoformat(),
    }


def _serialize_document_detail(document, access_status):
    current_revision = _get_current_revision(document)
    return {
        "id": document.id,
        "code": document.code,
        "title": document.title,
        "description": document.description or "",
        "project": {
            "id": document.project_id,
            "code": document.project.code,
            "name": document.project.name,
        },
        "discipline": {
            "id": document.discipline_id,
            "code": document.discipline.code,
            "name": document.discipline.name,
        },
        "type": {
            "code": document.document_type.code,
            "name": document.document_type.name,
        },
        "confidentiality_level": document.confidentiality_level,
        "areas": [
            {"acronym": area.acronym, "name": area.name}
            for area in document.areas.all()
            if area.active
        ],
        "responsible": {
            "id": document.responsible_id,
            "name": document.responsible.name,
            "email": document.responsible.email,
        },
        "revision": _serialize_revision(current_revision) if current_revision else None,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "access_status": access_status,
    }


def get_document_detail(document_id, user_id=None):
    document = _get_document_or_none(document_id)
    if document is None:
        raise DocumentNotFoundError()

    user = None
    if user_id:
        user = User.objects.filter(pk=user_id).first()

    access_status = _compute_access_status(document, user)
    return _serialize_document_detail(document, access_status)


def request_document_access(document_id, user_id, justification=""):
    document = _get_document_or_none(document_id)
    if document is None:
        raise DocumentNotFoundError()

    if not user_id:
        raise MissingUserError()

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise UserNotFoundError() from exc

    access, created = DocumentAccess.objects.get_or_create(
        document=document,
        user=user,
        defaults={
            "status": AccessStatus.PENDING,
            "justification": justification,
            "requested_at": timezone.now(),
        },
    )

    return {
        "id": access.id,
        "status": access.status,
        "created": created,
    }
