from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from core.models import Area, Document, DocumentType

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
