from core.models import LegalDocumentVersion, UserLegalAcceptance


def _isoformat(value):
    return value.isoformat() if value else None


def _serialize_document(document) -> dict:
    return {"slug": document.slug, "title": document.title}


def serialize_legal_version(version: LegalDocumentVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "document": _serialize_document(version.document),
        "summary": version.summary,
        "content_hash": version.content_hash,
        "published_at": _isoformat(version.published_at),
        "clauses": [
            {
                "id": clause.id,
                "code": clause.code,
                "position": clause.position,
                "title": clause.title,
                "body": clause.body,
                "is_required": clause.is_required,
            }
            for clause in version.clauses.all()
        ],
    }


def serialize_acceptance(acceptance: UserLegalAcceptance) -> dict:
    version = acceptance.version
    return {
        "id": acceptance.id,
        "accepted_at": _isoformat(acceptance.accepted_at),
        "revoked_at": _isoformat(acceptance.revoked_at),
        "document": _serialize_document(version.document),
        "version": {
            "id": version.id,
            "version": version.version,
            "content_hash": version.content_hash,
            "published_at": _isoformat(version.published_at),
        },
        "consents": [
            {
                "clause_id": consent.clause_id,
                "code": consent.clause.code,
                "title": consent.clause.title,
                "is_required": consent.clause.is_required,
                "accepted": consent.accepted,
                "decided_at": _isoformat(consent.decided_at),
            }
            for consent in acceptance.clause_consents.all()
        ],
    }


def serialize_acceptance_history(acceptances) -> dict:
    results = [serialize_acceptance(acceptance) for acceptance in acceptances]
    return {"count": len(results), "results": results}
