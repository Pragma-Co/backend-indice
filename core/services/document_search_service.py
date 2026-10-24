import re

from django.contrib.postgres.aggregates import StringAgg
from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
    SearchVector,
)
from django.db.models import (
    BooleanField,
    Case,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Q,
    Subquery,
    TextField,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat

from core.models import Document, DocumentAccess, DocumentTag
from core.models.choices import AccessStatus
from core.models.search import ENGLISH_SEARCH_CONFIG, SEARCH_CONFIG
from core.serializers.document_search_serializer import (
    FRAGMENT_SEPARATOR,
    HIGHLIGHT_START,
    HIGHLIGHT_STOP,
    TAG_SEPARATOR,
    serialize_search_highlights,
)
from core.services.document_exceptions import DocumentQueryError
from core.services.document_index_service import thematic_tag_names
from core.services.documents_service import (
    filter_documents,
    paginate_documents,
    parse_document_query,
    serialize_document,
)

QUERY_MAX_LENGTH = 200
MAX_QUERY_TERMS = 12
TERM_PATTERN = re.compile(r"[^\W_]+")
SNIPPET_MAX_FRAGMENTS = 3
SNIPPET_MAX_WORDS = 30
SNIPPET_MIN_WORDS = 10
SCORE_DECIMALS = 4


def _error(code, message):
    return {"code": code, "message": message}


def _search_terms(params, errors):
    text = params.get("q", "").strip()
    if not text:
        errors["q"] = _error("required", "q is required.")
        return []
    if len(text) > QUERY_MAX_LENGTH:
        errors["q"] = _error("too_long", f"q must have at most {QUERY_MAX_LENGTH} characters.")
        return []
    terms = list(dict.fromkeys(TERM_PATTERN.findall(text)))[:MAX_QUERY_TERMS]
    if not terms:
        errors["q"] = _error("invalid", "q must contain at least one word.")
    return terms


def parse_search_query(params):
    errors = {}
    terms = _search_terms(params, errors)
    try:
        query = parse_document_query(params)
    except DocumentQueryError as exc:
        errors.update(exc.errors)
    if errors:
        raise DocumentQueryError(errors)
    return {**query, "search_term": "", "terms": terms}


def build_search_query(terms, config=SEARCH_CONFIG):
    search_query = None
    for term in terms:
        term_query = SearchQuery(term, config=config)
        search_query = term_query if search_query is None else search_query | term_query
    return search_query


def _tag_names(separator=" "):
    names = Subquery(
        DocumentTag.objects.filter(document=OuterRef("pk"))
        .values("document")
        .annotate(names=StringAgg("tag__name", separator))
        .values("names"),
        output_field=TextField(),
    )
    return Coalesce(names, Value(""), output_field=TextField())


def _metadata_vector():
    return (
        SearchVector("title", weight="A", config=SEARCH_CONFIG)
        + SearchVector("code", weight="A", config=SEARCH_CONFIG)
        + SearchVector(_tag_names(), weight="A", config=SEARCH_CONFIG)
        + SearchVector("description", weight="B", config=SEARCH_CONFIG)
    )


def _can_read(user):
    if user is None:
        return Value(False, output_field=BooleanField())
    approved_access = DocumentAccess.objects.filter(
        document=OuterRef("pk"), user=user, status=AccessStatus.APPROVED
    )
    return Case(
        When(responsible_id=user.id, then=Value(True)),
        When(Exists(approved_access), then=Value(True)),
        default=Value(False),
        output_field=BooleanField(),
    )


def apply_full_text_search(queryset, search_query, content_query, user):
    return (
        queryset.annotate(
            metadata_vector=_metadata_vector(),
            can_read=_can_read(user),
            thematic_tags=F("indexed_content__thematic_tags"),
        )
        .annotate(
            metadata_match=ExpressionWrapper(
                Q(metadata_vector=search_query), output_field=BooleanField()
            ),
            content_match=ExpressionWrapper(
                Q(indexed_content__search_vector=content_query),
                output_field=BooleanField(),
            ),
        )
        .filter(Q(metadata_match=True) | Q(content_match=True))
        .annotate(
            score=SearchRank(F("metadata_vector"), search_query)
            + Case(
                When(
                    content_match=True,
                    then=SearchRank(F("indexed_content__search_vector"), content_query),
                ),
                default=Value(0.0),
                output_field=FloatField(),
            )
        )
        .order_by("-score", "-updated_at", "-id")
    )


def _headline(field, search_query, config=SEARCH_CONFIG, **options):
    return SearchHeadline(
        field,
        search_query,
        config=config,
        start_sel=HIGHLIGHT_START,
        stop_sel=HIGHLIGHT_STOP,
        **options,
    )


def _content_headline(content_match_ids, query, config=SEARCH_CONFIG):
    return Case(
        When(
            pk__in=content_match_ids,
            then=_headline(
                "indexed_content__content",
                query,
                config,
                max_fragments=SNIPPET_MAX_FRAGMENTS,
                max_words=SNIPPET_MAX_WORDS,
                min_words=SNIPPET_MIN_WORDS,
                fragment_delimiter=FRAGMENT_SEPARATOR,
            ),
        ),
        default=Value(""),
        output_field=TextField(),
    )


def fetch_highlights(document_ids, content_match_ids, search_query, english_query):
    rows = (
        Document.objects.filter(pk__in=document_ids)
        .annotate(
            title_highlight=_headline("title", search_query, highlight_all=True),
            description_highlight=_headline("description", search_query, highlight_all=True),
            tags_highlight=_headline(
                Concat(
                    _tag_names(TAG_SEPARATOR),
                    Value(TAG_SEPARATOR),
                    Case(
                        When(
                            pk__in=content_match_ids,
                            then=thematic_tag_names(
                                "indexed_content__thematic_tags", TAG_SEPARATOR
                            ),
                        ),
                        default=Value(""),
                        output_field=TextField(),
                    ),
                    output_field=TextField(),
                ),
                search_query,
                highlight_all=True,
            ),
            content_highlight=_content_headline(content_match_ids, search_query),
            content_highlight_en=_content_headline(
                content_match_ids, english_query, ENGLISH_SEARCH_CONFIG
            ),
        )
        .values(
            "pk",
            "title_highlight",
            "description_highlight",
            "tags_highlight",
            "content_highlight",
            "content_highlight_en",
        )
    )
    return {row["pk"]: serialize_search_highlights(row) for row in rows}


def _serialize_result(document):
    return {
        **serialize_document(document),
        "score": round(document.score, SCORE_DECIMALS),
        "tags": [tag.name for tag in document.tags.all()],
        "thematic_tags": list(document.thematic_tags or []) if document.can_read else [],
        "content_match": document.content_match,
        "can_read": document.can_read,
    }


def search_documents(params, user=None):
    query = parse_search_query(params)
    search_query = build_search_query(query["terms"])
    english_query = build_search_query(query["terms"], ENGLISH_SEARCH_CONFIG)
    content_query = search_query | english_query
    queryset = apply_full_text_search(filter_documents(query), search_query, content_query, user)
    page = paginate_documents(queryset, query, _serialize_result)

    document_ids = [result["id"] for result in page["results"]]
    content_match_ids = [
        result["id"]
        for result in page["results"]
        if result["content_match"] and result["can_read"]
    ]
    highlights = fetch_highlights(document_ids, content_match_ids, search_query, english_query)
    for result in page["results"]:
        highlight = highlights[result["id"]]
        result.pop("can_read")
        matched_tags = highlight.pop("matched_tags")
        result["matched_tags"] = list(
            dict.fromkeys(
                tag for tag in result["tags"] + result["thematic_tags"] if tag in matched_tags
            )
        )
        result["highlights"] = highlight
    return {"query": params.get("q", "").strip(), **page}
