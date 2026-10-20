from django.core.paginator import Paginator
from django.db.models import Q

from core.models import AuditAction, AuditLog, Document, DocumentAccess, Revision
from core.serializers.manager_activity_serializer import serialize_activity_page
from core.services.audit_service import (
    ENTITY_DOCUMENT,
    ENTITY_TEMP_UPLOAD,
    EVENT_AI_CLASSIFICATION,
    EVENT_CONTENT_INDEXED,
)
from core.services.document_code_service import revision_label
from core.services.document_text_service import (
    EXTRACTION_EMPTY,
    EXTRACTION_FAILURE,
    EXTRACTION_SKIPPED,
    EXTRACTION_SUCCESS,
)
from core.services.manager_activity_exceptions import ActivityQueryError

UPLOAD = "UPLOAD"
REVISION = "REVISION"
INGESTION_FAILURE = "INGESTION_FAILURE"
MODERATION = "MODERATION"
ACCESS = "ACCESS"
EVENT_TYPES = (UPLOAD, REVISION, INGESTION_FAILURE, MODERATION, ACCESS)

SUCCESS = "SUCCESS"
PROCESSING = "PROCESSING"
FAILURE = "FAILURE"

ENTITY_REVISION = "revision"
ENTITY_DOCUMENT_ACCESS = "document_access"

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

REVISION_DECISIONS = ("REVISION_APPROVED", "REVISION_REJECTED")
ACCESS_DECISIONS = ("ACCESS_APPROVED", "ACCESS_REJECTED")
ARCHIVING_EVENTS = ("DOCUMENT_ARCHIVED", "DOCUMENT_RESTORED")
MODERATION_EVENTS = REVISION_DECISIONS + ACCESS_DECISIONS + ARCHIVING_EVENTS
EVENT_ACCESS_DENIED = "DOCUMENT_ACCESS_DENIED"
COMPLETED_EXTRACTIONS = (EXTRACTION_SUCCESS, EXTRACTION_EMPTY, EXTRACTION_SKIPPED)
COMPLETED_CLASSIFICATIONS = (SUCCESS, "SKIPPED")


def _without_event():
    return Q(record__isnull=True) | Q(record__event__isnull=True)


TYPE_FILTERS = {
    UPLOAD: (
        Q(action=AuditAction.DOC_UPLOAD_SUCCESS, record__ingestion__isnull=True)
        | Q(
            action=AuditAction.DOC_UPLOAD_SUCCESS,
            record__ingestion__extraction__in=COMPLETED_EXTRACTIONS,
        )
        | Q(action=AuditAction.DOC_UPLOAD_DUPLICATE)
        | Q(action=AuditAction.DOC_SUBMIT_SUCCESS)
        | Q(action=AuditAction.CREATE, entity=ENTITY_DOCUMENT)
        | Q(
            entity=ENTITY_TEMP_UPLOAD,
            record__event=EVENT_AI_CLASSIFICATION,
            record__status__in=COMPLETED_CLASSIFICATIONS,
        )
        | Q(record__event=EVENT_CONTENT_INDEXED, record__status=SUCCESS)
    ),
    REVISION: (
        Q(action=AuditAction.DOC_REVISION_CREATED)
        | Q(action=AuditAction.CREATE, entity=ENTITY_REVISION)
    ),
    INGESTION_FAILURE: (
        Q(action=AuditAction.DOC_UPLOAD_SUCCESS, record__ingestion__extraction=EXTRACTION_FAILURE)
        | Q(
            entity=ENTITY_TEMP_UPLOAD, record__event=EVENT_AI_CLASSIFICATION, record__status=FAILURE
        )
        | Q(record__event=EVENT_CONTENT_INDEXED, record__status=FAILURE)
    ),
    MODERATION: (
        Q(record__event__in=MODERATION_EVENTS)
        | (
            Q(action=AuditAction.UPDATE, entity__in=[ENTITY_REVISION, ENTITY_DOCUMENT_ACCESS])
            & _without_event()
        )
        | (Q(action=AuditAction.DELETE, entity=ENTITY_DOCUMENT) & _without_event())
    ),
    ACCESS: (
        Q(action=AuditAction.DOC_ACCESS_REQUESTED)
        | Q(record__event=EVENT_ACCESS_DENIED)
        | Q(action=AuditAction.DOC_DOWNLOAD)
        | Q(action=AuditAction.READ, entity=ENTITY_DOCUMENT)
        | Q(action=AuditAction.CREATE, entity=ENTITY_DOCUMENT_ACCESS)
    ),
}


def _error(code, message):
    return {"code": code, "message": message}


def _positive_int(params, name, default, errors):
    raw = (params.get(name) or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def _values(params, name):
    getlist = getattr(params, "getlist", None)
    raw_values = getlist(name) + getlist(f"{name}[]") if getlist else [params.get(name) or ""]
    values = []
    for raw in raw_values:
        for piece in str(raw).split(","):
            value = piece.strip().upper()
            if value and value not in values:
                values.append(value)
    return values


def parse_activity_query(params) -> dict:
    errors = {}
    page = _positive_int(params, "page", 1, errors)
    size_name = "page_size" if (params.get("page_size") or "").strip() else "limit"
    page_size = _positive_int(params, size_name, DEFAULT_PAGE_SIZE, errors)
    if page_size > MAX_PAGE_SIZE:
        errors[size_name] = _error("too_large", f"{size_name} must be at most {MAX_PAGE_SIZE}.")
    types = _values(params, "type")
    if any(event_type not in EVENT_TYPES for event_type in types):
        errors["type"] = _error("invalid_choice", f"type must be one of {list(EVENT_TYPES)}.")
    if errors:
        raise ActivityQueryError(errors)
    return {"page": page, "page_size": page_size, "types": types}


def area_scope(manager) -> Q:
    area_id = manager.area_id
    return (
        Q(
            entity=ENTITY_DOCUMENT,
            entity_id__in=Document.objects.filter(document_areas__area_id=area_id).values("pk"),
        )
        | Q(
            entity=ENTITY_REVISION,
            entity_id__in=Revision.objects.filter(document__document_areas__area_id=area_id).values(
                "pk"
            ),
        )
        | Q(
            entity=ENTITY_DOCUMENT_ACCESS,
            entity_id__in=DocumentAccess.objects.filter(
                document__document_areas__area_id=area_id
            ).values("pk"),
        )
        | Q(entity=ENTITY_TEMP_UPLOAD, user__area_id=area_id)
    )


def activity_entries(manager, types=()):
    type_filter = Q()
    for event_type in types or EVENT_TYPES:
        type_filter |= TYPE_FILTERS[event_type]
    return (
        AuditLog.objects.filter(area_scope(manager))
        .filter(type_filter)
        .select_related("user")
        .order_by("-occurred_at", "-id")
    )


def _load_references(entries) -> dict:
    ids = {ENTITY_DOCUMENT: set(), ENTITY_REVISION: set(), ENTITY_DOCUMENT_ACCESS: set()}
    for entry in entries:
        if entry.entity in ids and entry.entity_id is not None:
            ids[entry.entity].add(entry.entity_id)
    revisions = {
        revision.pk: revision
        for revision in Revision.objects.filter(pk__in=ids[ENTITY_REVISION]).select_related(
            "document"
        )
    }
    accesses = {
        access.pk: access
        for access in DocumentAccess.objects.filter(
            pk__in=ids[ENTITY_DOCUMENT_ACCESS]
        ).select_related("document")
    }
    document_ids = (
        ids[ENTITY_DOCUMENT]
        | {revision.document_id for revision in revisions.values()}
        | {access.document_id for access in accesses.values()}
    )
    documents = {document.pk: document for document in Document.objects.filter(pk__in=document_ids)}
    return {"documents": documents, "revisions": revisions, "accesses": accesses}


def _resolve_document(entry, references):
    if entry.entity == ENTITY_DOCUMENT:
        return references["documents"].get(entry.entity_id), None
    if entry.entity == ENTITY_REVISION:
        revision = references["revisions"].get(entry.entity_id)
        return (revision.document if revision else None), revision
    if entry.entity == ENTITY_DOCUMENT_ACCESS:
        access = references["accesses"].get(entry.entity_id)
        return (access.document if access else None), None
    return None, None


def _description(event_type, status, event, detail, **extra) -> dict:
    return {
        "event_type": event_type,
        "status": status,
        "event": event,
        "detail": detail,
        "document": extra.get("document"),
        "code": extra.get("code"),
        "revision": extra.get("revision"),
        "file": extra.get("file"),
    }


def _decision_word(event) -> str:
    if event.endswith("APPROVED"):
        return "approved"
    if event.endswith("REJECTED"):
        return "rejected"
    return "decided"


def _with_justification(detail, record) -> str:
    justification = (record.get("justification") or "").strip()
    return f"{detail} Justification: {justification}" if justification else detail


def describe_entry(entry, references) -> dict:
    record = entry.record or {}
    event = record.get("event")
    action = entry.action
    document, revision = _resolve_document(entry, references)
    code = document.code if document else record.get("document_code") or record.get("code")
    version = record.get("version") or (revision.version if revision else None)
    label = revision_label(version) if version is not None else None
    refs = {"document": document, "code": code, "revision": label}
    file_name = record.get("original_name") or (record.get("original_names") or [None])[0]

    if action == AuditAction.DOC_UPLOAD_SUCCESS:
        ingestion = record.get("ingestion") or {}
        if ingestion.get("extraction") == EXTRACTION_FAILURE:
            detail = ingestion.get("detail") or "Text extraction failed."
            return _description(
                INGESTION_FAILURE, FAILURE, "TEXT_EXTRACTION_FAILED", detail, file=file_name, **refs
            )
        detail = f"File {file_name or ''} uploaded.".replace("  ", " ")
        if ingestion.get("detail"):
            detail = f"{detail} {ingestion['detail']}"
        return _description(UPLOAD, SUCCESS, "FILE_UPLOADED", detail, file=file_name, **refs)
    if action == AuditAction.DOC_UPLOAD_DUPLICATE:
        detail = f"Duplicate file refused: already registered in document {code}."
        return _description(
            UPLOAD, FAILURE, "DUPLICATE_FILE_REFUSED", detail, file=file_name, **refs
        )
    if event == EVENT_AI_CLASSIFICATION:
        status = record.get("status")
        if status == FAILURE:
            detail = record.get("detail") or "AI classification failed."
            return _description(INGESTION_FAILURE, FAILURE, "AI_CLASSIFICATION_FAILED", detail)
        if status == SUCCESS:
            return _description(
                UPLOAD, SUCCESS, "AI_CLASSIFICATION_DONE", "Metadata suggested from the content."
            )
        detail = record.get("detail") or "AI classification skipped."
        return _description(UPLOAD, SUCCESS, "AI_CLASSIFICATION_SKIPPED", detail)
    if event == EVENT_CONTENT_INDEXED:
        if record.get("status") == FAILURE:
            detail = record.get("detail") or "Content indexing failed."
            return _description(
                INGESTION_FAILURE, FAILURE, "CONTENT_INDEXING_FAILED", detail, **refs
            )
        detail = record.get("detail") or "Content indexed."
        return _description(UPLOAD, SUCCESS, "CONTENT_INDEXED", detail, **refs)
    if action == AuditAction.DOC_SUBMIT_SUCCESS or (
        action == AuditAction.CREATE and entry.entity == ENTITY_DOCUMENT
    ):
        suffix = f" with revision {label}" if label else ""
        return _description(
            UPLOAD, SUCCESS, "DOCUMENT_REGISTERED", f"Document {code} registered{suffix}.", **refs
        )
    if action == AuditAction.DOC_REVISION_CREATED or (
        action == AuditAction.CREATE and entry.entity == ENTITY_REVISION
    ):
        detail = f"Revision {label} of document {code} submitted."
        return _description(REVISION, SUCCESS, "REVISION_SUBMITTED", detail, **refs)
    if event in REVISION_DECISIONS or (
        action == AuditAction.UPDATE and entry.entity == ENTITY_REVISION
    ):
        decision = event or f"REVISION_{record.get('status') or 'DECIDED'}"
        detail = f"Revision {label} of document {code} {_decision_word(decision)}."
        return _description(
            MODERATION, SUCCESS, decision, _with_justification(detail, record), **refs
        )
    if event in ACCESS_DECISIONS or (
        action == AuditAction.UPDATE and entry.entity == ENTITY_DOCUMENT_ACCESS
    ):
        decision = event or f"ACCESS_{record.get('status') or 'DECIDED'}"
        detail = f"Access request for document {code} {_decision_word(decision)}."
        return _description(MODERATION, SUCCESS, decision, detail, **refs)
    if event in ARCHIVING_EVENTS or (
        action == AuditAction.DELETE and entry.entity == ENTITY_DOCUMENT
    ):
        archived = event != "DOCUMENT_RESTORED"
        detail = f"Document {code} {'archived' if archived else 'restored'}."
        return _description(MODERATION, SUCCESS, event or "DOCUMENT_ARCHIVED", detail, **refs)
    if action == AuditAction.DOC_ACCESS_REQUESTED or (
        action == AuditAction.CREATE and entry.entity == ENTITY_DOCUMENT_ACCESS
    ):
        detail = _with_justification(f"Access to document {code} requested.", record)
        return _description(ACCESS, SUCCESS, "ACCESS_REQUESTED", detail, **refs)
    if event == EVENT_ACCESS_DENIED:
        detail = f"Access to document {code} denied."
        return _description(ACCESS, FAILURE, EVENT_ACCESS_DENIED, detail, **refs)
    if action == AuditAction.DOC_DOWNLOAD:
        detail = f"Document {code} downloaded."
        return _description(ACCESS, SUCCESS, "DOCUMENT_DOWNLOADED", detail, **refs)
    if action == AuditAction.READ and entry.entity == ENTITY_DOCUMENT:
        detail = f"Document {code} viewed."
        return _description(ACCESS, SUCCESS, "DOCUMENT_VIEWED", detail, **refs)
    return _description(None, SUCCESS, event or action, "", **refs)


def list_activities(manager, params) -> dict:
    query = parse_activity_query(params)
    paginator = Paginator(activity_entries(manager, query["types"]), query["page_size"])
    page_number = query["page"]
    entries = (
        list(paginator.page(page_number).object_list) if page_number <= paginator.num_pages else []
    )
    references = _load_references(entries)
    descriptions = {entry.pk: describe_entry(entry, references) for entry in entries}
    return serialize_activity_page(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_number,
            "page_size": query["page_size"],
            "results": entries,
        },
        descriptions,
    )
