from datetime import timedelta
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Area, SearchHistory, User
from core.services.search_history_service import (
    SEARCH_HISTORY_LIMIT,
    list_search_history,
    record_search,
)


class SearchHistoryTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="HIS", name="History")
        self.user = User.objects.create_user(
            email="user@example.com", password="password", name="User", area=area
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="password", name="Other", area=area
        )
        self.client.force_login(self.user)

    def test_records_searches_and_returns_most_recent_first(self):
        now = timezone.now()
        with mock.patch("core.services.search_history_service.timezone.now") as clock:
            clock.return_value = now
            record_search(self.user, "first")
            clock.return_value = now + timedelta(seconds=1)
            record_search(self.user, "second")

        response = self.client.get(reverse("user-search-history"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": ["second", "first"]})

    def test_repeated_search_updates_display_and_moves_to_front(self):
        now = timezone.now()
        with mock.patch("core.services.search_history_service.timezone.now") as clock:
            clock.return_value = now
            record_search(self.user, "  Steel   Bridge  ")
            clock.return_value = now + timedelta(seconds=1)
            record_search(self.user, "concrete")
            clock.return_value = now + timedelta(seconds=2)
            record_search(self.user, "steel bridge")

        self.assertEqual(list_search_history(self.user), ["steel bridge", "concrete"])
        self.assertEqual(SearchHistory.objects.filter(user=self.user).count(), 2)

    def test_limit_and_user_isolation(self):
        record_search(self.other_user, "private")
        now = timezone.now()
        with mock.patch("core.services.search_history_service.timezone.now") as clock:
            for index in range(SEARCH_HISTORY_LIMIT + 2):
                clock.return_value = now + timedelta(seconds=index)
                record_search(self.user, f"query {index}")

        expected = [f"query {index}" for index in range(SEARCH_HISTORY_LIMIT + 1, 1, -1)]
        self.assertEqual(
            self.client.get(reverse("user-search-history")).json(), {"results": expected}
        )
        self.assertEqual(SearchHistory.objects.filter(user=self.user).count(), SEARCH_HISTORY_LIMIT)
        self.assertEqual(list_search_history(self.other_user), ["private"])

    def test_repeated_search_moves_to_front_with_same_timestamp(self):
        now = timezone.now()
        with mock.patch("core.services.search_history_service.timezone.now", return_value=now):
            record_search(self.user, "first")
            record_search(self.user, "second")
            record_search(self.user, "first")
        self.assertEqual(list_search_history(self.user), ["first", "second"])

    def test_inactive_user_cannot_create_history(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        record_search(self.user, "private")
        self.assertEqual(list_search_history(self.user), [])

    def test_endpoint_requires_authentication_and_only_allows_get(self):
        url = reverse("user-search-history")
        self.assertEqual(Client().get(url).status_code, 401)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.get(url).json(), {"results": []})

    def test_document_search_records_only_successful_queries(self):
        search_url = reverse("document-search")
        self.assertEqual(self.client.get(search_url, {"q": "  bridge  "}).status_code, 200)
        self.assertEqual(self.client.get(search_url, {"q": "!!!"}).status_code, 400)
        self.assertEqual(
            self.client.get(search_url, {"q": "bridge", "page": "bad"}).status_code, 400
        )
        self.assertEqual(list_search_history(self.user), ["bridge"])

    def test_history_failure_does_not_break_search(self):
        with mock.patch("core.views.documents_view.record_search", side_effect=RuntimeError):
            with self.assertLogs("core.views.documents_view", level="ERROR"):
                response = self.client.get(reverse("document-search"), {"q": "bridge"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_search_history(self.user), [])
