from datetime import date, datetime, time, timedelta

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Revision,
    User,
)
from core.models.choices import AccessStatus, RevisionStatus
from core.serializers.document_serializer import revision_label
from core.services.document_exceptions import DocumentQueryError
from core.services.documents_exceptions import (
    AlreadyHasAccessError,
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)

SIMPLE_FILTERS_CACHE_KEY = "documents:simple-filters:v2"
SIMPLE_FILTERS_CACHE_TIMEOUT = 300
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DATE_FILTERS = [
    {"value": "last_7_days", "label": "Últimos 7 dias"},
    {"value": "last_month", "label": "Último mês"},
    {"value": "last_year", "label": "Último ano"},
]


STATUS_FILTERS = [
    {"value": RevisionStatus.PENDING.value, "label": "Em revisão"},
    {"value": RevisionStatus.APPROVED.value, "label": "Vigente"},
    {"value": RevisionStatus.REJECTED.value, "label": "Rejeitado"},
    {"value": RevisionStatus.OBSOLETE.value, "label": "Obsoleto"},
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
        "disciplines": list(
            Discipline.objects.filter(active=True).order_by("code").values("code", "name")
        ),
        "statuses": STATUS_FILTERS,
        "dates": DATE_FILTERS,
    }


def get_simple_filters():
    payload = cache.get(SIMPLE_FILTERS_CACHE_KEY)
    if payload is None:
        payload = build_simple_filters()
        cache.set(SIMPLE_FILTERS_CACHE_KEY, payload, SIMPLE_FILTERS_CACHE_TIMEOUT)
    return payload


def _error(code, message):
    return {"code": code, "message": message}


def _positive_int(params, name, default, errors):
    raw = params.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def _first_present(params, names):
    for name in names:
        if params.get(name, "").strip():
            return name
    return names[0]


def _iso_date(params, names, errors):
    name = _first_present(params, names)
    raw = params.get(name, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors[name] = _error("invalid", f"{name} must be a date in the YYYY-MM-DD format.")
        return None


def _date_preset(params, errors):
    raw = params.get("data", "").strip()
    if raw and raw not in DATE_RANGES:
        errors["data"] = _error("invalid_choice", f"data must be one of {sorted(DATE_RANGES)}.")
        return ""
    return raw


def _raw_values(params, name):
    getlist = getattr(params, "getlist", None)
    if getlist is None:
        raw = params.get(name, "")
        return raw if isinstance(raw, list) else [raw]
    return getlist(name) + getlist(f"{name}[]")


def _multiple(params, name, normalize=str.upper):
    values = []
    for raw in _raw_values(params, name):
        for piece in str(raw).split(","):
            value = normalize(piece.strip())
            if value and value not in values:
                values.append(value)
    return values


def _statuses(params, errors):
    statuses = _multiple(params, "status")
    unknown = sorted(set(statuses) - set(RevisionStatus.values))
    if unknown:
        errors["status"] = _error(
            "invalid_choice", f"status must be among {sorted(RevisionStatus.values)}."
        )
        return []
    return statuses


def _responsible_id(params, errors):
    raw = params.get("responsible_id", "").strip()
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < 1:
        errors["responsible_id"] = _error("invalid", "responsible_id must be a positive integer.")
        return None
    return int(raw)


def _created_by_id(params, errors):
    raw = params.get("created_by_id", "").strip()
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < 1:
        errors["created_by_id"] = _error("invalid", "created_by_id must be a positive integer.")
        return None
    return int(raw)


def parse_document_query(params):
    errors = {}
    query = {
        "search_term": params.get("q", "").strip(),
        "areas": _multiple(params, "area"),
        "document_types": _multiple(params, "tipo"),
        "disciplines": _multiple(params, "discipline"),
        "statuses": _statuses(params, errors),
        "tags": _multiple(params, "tags", normalize=str),
        "responsible_id": _responsible_id(params, errors),
        "created_by_id": _created_by_id(params, errors),
        "date_preset": _date_preset(params, errors),
        "date_from": _iso_date(params, ("date_from", "data_inicio"), errors),
        "date_to": _iso_date(params, ("date_to", "data_fim"), errors),
        "page": _positive_int(params, "page", 1, errors),
        "page_size": min(
            _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors), MAX_PAGE_SIZE
        ),
    }
    if query["date_from"] and query["date_to"] and query["date_from"] > query["date_to"]:
        name = _first_present(params, ("date_to", "data_fim"))
        errors[name] = _error("invalid_range", f"{name} must not be earlier than the start date.")
    if errors:
        raise DocumentQueryError(errors)
    return query


def _start_of_day(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def filter_documents(query):
    latest_revision = Revision.objects.filter(document=OuterRef("pk")).order_by("-version")
    queryset = (
        Document.objects.filter(document_type__active=True)
        .filter(Q(areas__active=True) | Q(areas__isnull=True))
        .annotate(
            status=Subquery(latest_revision.values("status")[:1]),
            latest_version=Subquery(latest_revision.values("version")[:1]),
        )
        .select_related("document_type", "discipline", "project", "created_by", "updated_by")
        .prefetch_related("areas", "tags")
        .order_by("-updated_at", "-id")
        .distinct()
    )

    criteria = Q()
    if query["search_term"]:
        term = query["search_term"]
        criteria &= (
            Q(title__icontains=term)
            | Q(code__icontains=term)
            | Q(description__icontains=term)
            | Q(tags__name__icontains=term)
        )
    if query["document_types"]:
        criteria &= Q(document_type__code__in=query["document_types"])
    if query["disciplines"]:
        criteria &= Q(discipline__code__in=query["disciplines"])
    if query["statuses"]:
        criteria &= Q(status__in=query["statuses"])
    if query["responsible_id"]:
        criteria &= Q(responsible_id=query["responsible_id"])
    if query["created_by_id"]:
        criteria &= Q(created_by_id=query["created_by_id"])
    if query["date_preset"]:
        criteria &= Q(created_at__gte=timezone.now() - DATE_RANGES[query["date_preset"]])
    if query["date_from"]:
        criteria &= Q(created_at__gte=_start_of_day(query["date_from"]))
    if query["date_to"]:
        criteria &= Q(created_at__lt=_start_of_day(query["date_to"] + timedelta(days=1)))
    queryset = queryset.filter(criteria)

    if query["areas"]:
        queryset = queryset.filter(areas__active=True, areas__acronym__in=query["areas"])

    if query["tags"]:
        any_tag = Q()
        for tag in query["tags"]:
            any_tag |= Q(tags__name__iexact=tag)
        queryset = queryset.filter(any_tag)

    return queryset


def get_documents(params):
    query = parse_document_query(params)
    paginator = Paginator(filter_documents(query), query["page_size"])
    page_number = query["page"]
    page_items = paginator.page(page_number) if page_number <= paginator.num_pages else []

    return {
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_number,
        "page_size": query["page_size"],
        "results": [_serialize_document(document) for document in page_items],
    }


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
        "discipline": {
            "code": document.discipline.code,
            "name": document.discipline.name,
        },
        "areas": [
            {"acronym": area.acronym, "name": area.name}
            for area in document.areas.all()
            if area.active
        ],
        "revision": None
        if document.latest_version is None
        else {
            "version": document.latest_version,
            "label": revision_label(document.latest_version),
        },
        "status": document.status,
        "updated_at": document.updated_at.isoformat(),
        "created_by": {
            "id": document.created_by_id,
            "name": document.created_by.name if document.created_by else None,
        },
        "updated_by": {
            "id": document.updated_by_id,
            "name": document.updated_by.name if document.updated_by else None,
        },
    }


ACCESS_APPROVED = "APPROVED"
ACCESS_IN_REVIEW = "IN_REVIEW"
ACCESS_PENDING = "PENDING"


def _get_document_or_none(document_id):
    return (
        Document.objects.filter(document_type__active=True)
        .select_related(
            "project", "discipline", "document_type", "responsible", "created_by", "updated_by"
        )
        .prefetch_related(
            "areas",
            Prefetch(
                "revisions",
                queryset=Revision.objects.select_related("author", "auditor")
                .prefetch_related("files")
                .order_by("-version"),
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


def can_view_document(document, user):
    return _compute_access_status(document, user) == ACCESS_APPROVED


def resolve_user(user_id):
    if not user_id:
        raise MissingUserError()
    try:
        return User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise UserNotFoundError() from exc


def _latest_access_request(document, user):
    if user is None:
        return None
    access = DocumentAccess.objects.filter(document=document, user=user).first()
    if access is None:
        return None
    requested = access.requested_at or access.decided_at
    return {
        "id": access.id,
        "status": access.status,
        "created_at": requested.isoformat() if requested else None,
    }


def _serialize_file(file):
    return {
        "id": file.id,
        "original_name": file.original_name,
        "extension": file.extension,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "sha256": file.sha256,
        "view_url": f"/api/files/{file.id}/view",
    }


def _serialize_revision(revision, can_read):
    serialized = {
        "id": revision.id,
        "version": revision.version,
        "status": revision.status,
        "issue_date": revision.issue_date.isoformat() if revision.issue_date else None,
        "author": {"id": revision.author_id, "name": revision.author.name},
        "auditor": (
            {"id": revision.auditor_id, "name": revision.auditor.name}
            if revision.auditor_id
            else None
        ),
        "auditor_comment": revision.auditor_comment or "",
        "audited_at": revision.audited_at.isoformat() if revision.audited_at else None,
        "created_at": revision.created_at.isoformat(),
    }
    if can_read:
        serialized["change_description"] = revision.change_description
        serialized["files"] = [_serialize_file(f) for f in revision.files.all()]
    return serialized


def _serialize_document_detail(document, access_status, can_read, access_request):
    current_revision = _get_current_revision(document)
    serialized = {
        "id": document.id,
        "code": document.code,
        "title": document.title,
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
        "created_by": {
            "id": document.created_by_id,
            "name": document.created_by.name,
        },
        "updated_by": {
            "id": document.updated_by_id,
            "name": document.updated_by.name,
        },
        "revision": (_serialize_revision(current_revision, can_read) if current_revision else None),
        "versions": [
            _serialize_revision(revision, can_read) for revision in document.revisions.all()
        ],
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "access_status": access_status,
        "access_request": access_request,
    }
    if can_read:
        serialized["description"] = document.description or ""
    return serialized


def get_document_detail(document_id, user_id=None):
    document = _get_document_or_none(document_id)
    if document is None:
        raise DocumentNotFoundError()

    user = None
    if user_id:
        user = User.objects.filter(pk=user_id).first()

    access_status = _compute_access_status(document, user)
    can_read = access_status == ACCESS_APPROVED
    return _serialize_document_detail(
        document, access_status, can_read, _latest_access_request(document, user)
    )


def request_document_access(document_id, user_id, justification=""):
    document = _get_document_or_none(document_id)
    if document is None:
        raise DocumentNotFoundError()

    user = resolve_user(user_id)
    if can_view_document(document, user):
        raise AlreadyHasAccessError()

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
