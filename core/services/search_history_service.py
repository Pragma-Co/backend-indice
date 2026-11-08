from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import SearchHistory, User

SEARCH_HISTORY_LIMIT = 10


def record_search(user, term):
    term = term.strip()
    normalized_term = " ".join(term.split()).casefold()
    if not normalized_term:
        return

    with transaction.atomic():
        if not User.objects.select_for_update().filter(pk=user.pk, is_active=True).first():
            return
        latest = (
            SearchHistory.objects.filter(user=user)
            .order_by("-searched_at")
            .values_list("searched_at", flat=True)
            .first()
        )
        searched_at = timezone.now()
        if latest is not None and searched_at <= latest:
            searched_at = latest + timedelta(microseconds=1)
        SearchHistory.objects.update_or_create(
            user=user,
            normalized_term=normalized_term,
            defaults={"term": term, "searched_at": searched_at},
        )
        recent_ids = list(
            SearchHistory.objects.filter(user=user)
            .order_by("-searched_at", "-id")
            .values_list("id", flat=True)[:SEARCH_HISTORY_LIMIT]
        )
        SearchHistory.objects.filter(user=user).exclude(id__in=recent_ids).delete()


def list_search_history(user):
    return list(
        SearchHistory.objects.filter(user=user)
        .order_by("-searched_at", "-id")
        .values_list("term", flat=True)[:SEARCH_HISTORY_LIMIT]
    )
