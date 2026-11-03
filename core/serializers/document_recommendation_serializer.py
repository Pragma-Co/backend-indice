from core.services.documents_service import serialize_document

SCORE_DECIMALS = 2


def serialize_recommended_document(document, match):
    return {
        **serialize_document(document),
        "score": round(match["score"], SCORE_DECIMALS),
        "matches": {
            "project": match["project"],
            "discipline": match["discipline"],
            "type": match["type"],
            "tags": match["tags"],
            "areas": match["areas"],
            "themes": match["themes"],
        },
    }


def serialize_recommendation_collection(key, title, members, limit):
    return {
        "key": key,
        "title": title,
        "count": len(members),
        "items": [
            serialize_recommended_document(document, match) for document, match in members[:limit]
        ],
    }


def serialize_recommendations(document, limit, collections):
    return {
        "document": {"id": document.id, "code": document.code, "title": document.title},
        "limit": limit,
        "collections": collections,
    }
