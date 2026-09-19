from datetime import date, timedelta

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from core.models import Area, Document, DocumentType, Revision
from core.serializers.document_serializer import revision_label
from core.services.document_exceptions import DocumentQueryError

SIMPLE_FILTERS_CACHE_KEY = "documents:simple-filters"
SIMPLE_FILTERS_CACHE_TIMEOUT = 300
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
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


def _iso_date(params, name, errors):
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


def parse_document_query(params):
    errors = {}
    query = {
        "search_term": params.get("q", "").strip(),
        "area": params.get("area", "").strip(),
        "document_type": params.get("tipo", "").strip(),
        "date_preset": _date_preset(params, errors),
        "date_from": _iso_date(params, "date_from", errors),
        "date_to": _iso_date(params, "date_to", errors),
        "page": _positive_int(params, "page", 1, errors),
        "page_size": min(
            _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors), MAX_PAGE_SIZE
        ),
    }
    if errors:
        raise DocumentQueryError(errors)
    return query


def filter_documents(query):
    latest_revision = Revision.objects.filter(document=OuterRef("pk")).order_by("-version")
    queryset = (
        Document.objects.filter(document_type__active=True)
        .filter(Q(areas__active=True) | Q(areas__isnull=True))
        .annotate(
            status=Subquery(latest_revision.values("status")[:1]),
            latest_version=Subquery(latest_revision.values("version")[:1]),
        )
        .select_related("document_type", "discipline", "project")
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
    if query["document_type"]:
        criteria &= Q(document_type__code=query["document_type"])
    if query["date_preset"]:
        criteria &= Q(created_at__gte=timezone.now() - DATE_RANGES[query["date_preset"]])
    if query["date_from"]:
        criteria &= Q(created_at__date__gte=query["date_from"])
    if query["date_to"]:
        criteria &= Q(created_at__date__lte=query["date_to"])
    queryset = queryset.filter(criteria)

    if query["area"]:
        queryset = queryset.filter(areas__active=True, areas__acronym=query["area"])

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
    }
