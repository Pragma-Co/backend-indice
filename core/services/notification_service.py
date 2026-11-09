from django.core.paginator import Paginator
from django.utils import timezone

from core.models import AccessStatus, Notification, NotificationType, User
from core.services.document_code_service import revision_label
from core.services.notification_exceptions import (
    NotificationNotFoundError,
    NotificationValidationError,
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ACCESS_DECISION_TYPES = {
    AccessStatus.APPROVED: NotificationType.ACCESS_APPROVED,
    AccessStatus.REJECTED: NotificationType.ACCESS_REJECTED,
}
ACCESS_DECISION_WORDS = {
    AccessStatus.APPROVED: "aprovado",
    AccessStatus.REJECTED: "recusado",
}


def _error(code, message):
    return {"code": code, "message": message}


def notify_revision_published(revision, actor=None) -> list[Notification]:
    from core.services.document_visibility_service import is_visible

    document = revision.document
    savers = (
        User.objects.filter(is_active=True, saved_documents__document=document)
        .exclude(pk=getattr(actor, "pk", None))
        .order_by("id")
    )
    title = (
        f"Nova revisão ({revision_label(revision.version)}) publicada "
        f"para o documento {document.title}."
    )
    notifications = [
        Notification(
            recipient=saver,
            type=NotificationType.DOCUMENT_UPDATED,
            document=document,
            title=title,
        )
        for saver in savers
        if is_visible(document, saver)
    ]
    return Notification.objects.bulk_create(notifications)


def notify_access_decided(access) -> Notification | None:
    notification_type = ACCESS_DECISION_TYPES.get(access.status)
    if notification_type is None:
        return None
    document = access.document
    return Notification.objects.create(
        recipient=access.user,
        type=notification_type,
        document=document,
        title=(
            f"Seu pedido de acesso ao documento {document.title} foi "
            f"{ACCESS_DECISION_WORDS[access.status]}."
        ),
    )


def _positive_int(params, name, default, errors):
    raw = (params.get(name) or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def _unread_only(params, errors):
    raw = (params.get("unread") or "").strip().lower()
    if raw in ("", "false", "0"):
        return False
    if raw in ("true", "1"):
        return True
    errors["unread"] = _error("invalid", "unread must be true or false.")
    return False


def parse_notification_query(params) -> dict:
    errors = {}
    page = _positive_int(params, "page", 1, errors)
    page_size = _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors)
    if page_size > MAX_PAGE_SIZE:
        errors["page_size"] = _error("too_large", f"page_size must be at most {MAX_PAGE_SIZE}.")
    unread = _unread_only(params, errors)
    if errors:
        raise NotificationValidationError(errors)
    return {"page": page, "page_size": page_size, "unread": unread}


def user_notifications(user):
    return Notification.objects.filter(recipient=user)


def unread_count(user) -> int:
    return user_notifications(user).filter(read_at__isnull=True).count()


def list_notifications(user, params) -> dict:
    query = parse_notification_query(params)
    notifications = user_notifications(user).select_related("document")
    if query["unread"]:
        notifications = notifications.filter(read_at__isnull=True)
    paginator = Paginator(notifications.order_by("-created_at", "-id"), query["page_size"])
    page_number = query["page"]
    items = paginator.page(page_number).object_list if page_number <= paginator.num_pages else []
    return {
        "count": paginator.count,
        "unread_count": unread_count(user),
        "total_pages": paginator.num_pages,
        "current_page": page_number,
        "page_size": query["page_size"],
        "results": list(items),
    }


def mark_notification_as_read(user, notification_id) -> Notification:
    notification = (
        user_notifications(user).select_related("document").filter(pk=notification_id).first()
    )
    if notification is None:
        raise NotificationNotFoundError()
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def mark_all_notifications_as_read(user) -> int:
    return user_notifications(user).filter(read_at__isnull=True).update(read_at=timezone.now())
