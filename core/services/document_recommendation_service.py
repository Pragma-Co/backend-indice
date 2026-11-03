from django.db.models import F, Q

from core.models import Document
from core.serializers.document_recommendation_serializer import (
    serialize_recommendation_collection,
    serialize_recommendations,
)
from core.services.document_exceptions import DocumentQueryError
from core.services.documents_exceptions import DocumentNotFoundError
from core.services.documents_service import filter_documents, parse_document_query

DEFAULT_LIMIT = 8
MAX_LIMIT = 20

PROJECT_WEIGHT = 3.0
DISCIPLINE_WEIGHT = 2.0
TYPE_WEIGHT = 1.0
TAG_WEIGHT = 2.0
AREA_WEIGHT = 1.0
THEME_WEIGHT = 1.0

COLLECTION_THEME = "theme"
COLLECTION_PROJECT = "project"
COLLECTION_DISCIPLINE = "discipline"
COLLECTION_AREA = "area"

COLLECTIONS = (
    (COLLECTION_THEME, "Temas relacionados"),
    (COLLECTION_PROJECT, "Mesmo projeto"),
    (COLLECTION_DISCIPLINE, "Mesma disciplina"),
    (COLLECTION_AREA, "Mesma área"),
)


def parse_limit(params):
    raw = str(params.get("limit", "") or "").strip()
    if not raw:
        return DEFAULT_LIMIT
    if not raw.isdigit() or int(raw) < 1:
        raise DocumentQueryError(
            {"limit": {"code": "invalid", "message": "limit must be a positive integer."}}
        )
    return min(int(raw), MAX_LIMIT)


def get_document_or_raise(document_id):
    document = (
        Document.objects.filter(
            pk=document_id, document_type__active=True, archived_at__isnull=True
        )
        .select_related("indexed_content")
        .prefetch_related("tags", "areas")
        .first()
    )
    if document is None:
        raise DocumentNotFoundError()
    return document


def thematic_tags_of(document):
    content = getattr(document, "indexed_content", None)
    return list(content.thematic_tags) if content is not None else []


def affinity_profile(document):
    return {
        "tag_ids": {tag.id for tag in document.tags.all()},
        "area_ids": {area.id for area in document.areas.all() if area.active},
        "themes": thematic_tags_of(document),
    }


def related_candidates(document, profile):
    criteria = Q(project_id=document.project_id) | Q(discipline_id=document.discipline_id)
    if profile["tag_ids"]:
        criteria |= Q(tags__in=profile["tag_ids"])
    if profile["area_ids"]:
        criteria |= Q(areas__in=profile["area_ids"])
    if profile["themes"]:
        criteria |= Q(indexed_content__thematic_tags__overlap=profile["themes"])
    return (
        filter_documents(parse_document_query({}))
        .exclude(pk=document.pk)
        .filter(criteria)
        .annotate(themes=F("indexed_content__thematic_tags"))
    )


def affinity(candidate, document, profile):
    tags = sorted(tag.name for tag in candidate.tags.all() if tag.id in profile["tag_ids"])
    areas = sorted(area.acronym for area in candidate.areas.all() if area.id in profile["area_ids"])
    candidate_themes = set(candidate.themes or [])
    themes = [theme for theme in profile["themes"] if theme in candidate_themes]
    same_project = candidate.project_id == document.project_id
    same_discipline = candidate.discipline_id == document.discipline_id
    same_type = candidate.document_type_id == document.document_type_id
    score = (
        PROJECT_WEIGHT * same_project
        + DISCIPLINE_WEIGHT * same_discipline
        + TYPE_WEIGHT * same_type
        + TAG_WEIGHT * len(tags)
        + AREA_WEIGHT * len(areas)
        + THEME_WEIGHT * len(themes)
    )
    return {
        "score": score,
        "project": same_project,
        "discipline": same_discipline,
        "type": same_type,
        "tags": tags,
        "areas": areas,
        "themes": themes,
    }


def rank_candidates(document, profile):
    scored = [
        (candidate, affinity(candidate, document, profile))
        for candidate in related_candidates(document, profile)
    ]
    scored.sort(
        key=lambda entry: (
            -entry[1]["score"],
            -entry[0].updated_at.timestamp(),
            -entry[0].id,
        )
    )
    return scored


MEMBERSHIP = {
    COLLECTION_THEME: lambda match: bool(match["tags"] or match["themes"]),
    COLLECTION_PROJECT: lambda match: match["project"],
    COLLECTION_DISCIPLINE: lambda match: match["discipline"],
    COLLECTION_AREA: lambda match: bool(match["areas"]),
}


def build_collections(ranked, limit):
    collections = []
    for key, title in COLLECTIONS:
        members = [entry for entry in ranked if MEMBERSHIP[key](entry[1])]
        collections.append(serialize_recommendation_collection(key, title, members, limit))
    return collections


def get_document_recommendations(document_id, params):
    limit = parse_limit(params)
    document = get_document_or_raise(document_id)
    ranked = rank_candidates(document, affinity_profile(document))
    return serialize_recommendations(document, limit, build_collections(ranked, limit))
