from core.models import Notification


def _isoformat(value):
    return value.isoformat() if value else None


def serialize_notification(notification: Notification) -> dict:
    document = notification.document
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "document": {"id": document.id, "code": document.code, "title": document.title},
        "is_new": notification.is_new,
        "created_at": _isoformat(notification.created_at),
        "read_at": _isoformat(notification.read_at),
    }


def serialize_notification_page(page: dict) -> dict:
    return {**page, "results": [serialize_notification(item) for item in page["results"]]}
