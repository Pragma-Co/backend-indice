from datetime import UTC, datetime, timedelta

from django.test import TestCase
from django.urls import reverse

from core.models import AuditAction, Role
from core.services.decision_history_service import (
    list_decision_history,
    parse_decision_history_query,
)
from core.services.manager_activity_exceptions import ActivityQueryError
from core.tests.test_manager_activity import ManagerActivityFixtureMixin


class DecisionHistoryFixtureMixin(ManagerActivityFixtureMixin):
    def setUp(self):
        super().setUp()
        self.admin = self._user("admin@example.com", "Admin", Role.ADMIN, self.other_area)

    def _revision_decision(self, revision, event="REVISION_APPROVED", **kwargs):
        return self._entry(
            AuditAction.UPDATE,
            "revision",
            revision.pk,
            {
                "event": event,
                "document_code": revision.document.code,
                "version": revision.version,
                "justification": "Conforme a norma aplicável.",
            },
            user=kwargs.pop("user", self.manager),
            **kwargs,
        )

    def _access_decision(self, access, event="ACCESS_APPROVED", **kwargs):
        return self._entry(
            AuditAction.UPDATE,
            "document_access",
            access.pk,
            {"event": event, "document_code": access.document.code, "opinion": "Necessário."},
            user=kwargs.pop("user", self.manager),
            **kwargs,
        )

    def _history(self, params=None, manager=None):
        return list_decision_history(manager or self.manager, params or {})


class DecisionHistoryListingTests(DecisionHistoryFixtureMixin, TestCase):
    def test_should_list_revision_and_access_decisions_newest_first(self):
        self._revision_decision(self.revision, "REVISION_REJECTED", minutes_ago=30)
        self._access_decision(self.access, "ACCESS_APPROVED", minutes_ago=5)

        results = self._history()["results"]

        self.assertEqual([item["request_type"] for item in results], ["ACCESS", "REVISION"])
        self.assertEqual([item["decision"] for item in results], ["APPROVED", "REJECTED"])
        self.assertEqual(results[1]["revision"], "REV01")
        self.assertIsNone(results[0]["revision"])
        self.assertEqual(results[0]["document"]["code"], self.document.code)
        self.assertEqual(results[0]["user"], {"id": self.manager.pk, "name": "Manager"})
        self.assertEqual(results[0]["requester"], {"id": self.outsider.pk, "name": "Outsider"})
        self.assertEqual(results[1]["requester"], {"id": self.author.pk, "name": "Author"})
        self.assertEqual(results[0]["reason"], "Necessário.")
        self.assertEqual(results[1]["reason"], "Conforme a norma aplicável.")

    def test_should_leave_the_reason_empty_when_none_was_recorded(self):
        self._entry(
            AuditAction.UPDATE,
            "revision",
            self.revision.pk,
            {"event": "REVISION_APPROVED", "version": 1, "justification": "  "},
        )

        self.assertIsNone(self._history()["results"][0]["reason"])

    def test_should_ignore_events_that_are_not_decisions(self):
        self._entry(AuditAction.DOC_ACCESS_REQUESTED, "document_access", self.access.pk, {})
        self._entry(
            AuditAction.UPDATE,
            "document",
            self.document.pk,
            {"event": "DOCUMENT_ARCHIVED", "document_code": self.document.code},
        )
        self._entry(AuditAction.UPDATE, "revision", self.revision.pk, {"version": 1})

        self.assertEqual(self._history()["count"], 0)

    def test_should_keep_the_document_code_when_the_document_was_deleted(self):
        entry = self._revision_decision(self.revision)
        self.revision.delete()

        result = self._history(manager=self.admin)["results"][0]

        self.assertEqual(result["id"], entry.pk)
        self.assertEqual(result["document"]["code"], self.document.code)
        self.assertIsNone(result["document"]["id"])
        self.assertEqual(result["revision"], "REV01")

    def test_should_paginate(self):
        for minutes in range(5):
            self._revision_decision(self.revision, minutes_ago=minutes)

        body = self._history({"page": "2", "page_size": "2"})

        self.assertEqual(
            (body["count"], body["total_pages"], body["current_page"], len(body["results"])),
            (5, 3, 2, 2),
        )
        self.assertEqual(self._history({"page": "9", "page_size": "2"})["results"], [])


class DecisionHistoryScopeTests(DecisionHistoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teammate = self._user("mate@example.com", "Mate", Role.AUDITOR, self.area)
        self._revision_decision(self.revision)
        self._revision_decision(self.other_revision, user=self.teammate)
        self._revision_decision(self.revision, user=self.other_manager)

    def test_should_show_an_auditor_the_decisions_taken_by_the_own_area(self):
        users = {item["user"]["name"] for item in self._history()["results"]}

        self.assertEqual(users, {"Manager", "Mate"})

    def test_should_not_depend_on_the_area_of_the_decided_document(self):
        documents = {item["document"]["code"] for item in self._history()["results"]}

        self.assertEqual(documents, {self.document.code, self.other_document.code})

    def test_should_show_every_area_to_an_admin(self):
        self.assertEqual(self._history(manager=self.admin)["count"], 3)


class DecisionHistoryFilterTests(DecisionHistoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._revision_decision(self.revision, "REVISION_APPROVED", minutes_ago=10)
        self._revision_decision(self.revision, "REVISION_REJECTED", minutes_ago=20)
        self._access_decision(self.access, "ACCESS_APPROVED", minutes_ago=30)
        self._access_decision(self.access, "ACCESS_REJECTED", minutes_ago=40)

    def _pairs(self, params):
        return {(i["request_type"], i["decision"]) for i in self._history(params)["results"]}

    def test_should_filter_by_request_type(self):
        self.assertEqual(
            self._pairs({"request_type": "access"}),
            {("ACCESS", "APPROVED"), ("ACCESS", "REJECTED")},
        )

    def test_should_filter_by_decision(self):
        self.assertEqual(
            self._pairs({"decision": "REJECTED"}),
            {("REVISION", "REJECTED"), ("ACCESS", "REJECTED")},
        )

    def test_should_combine_type_and_decision(self):
        self.assertEqual(
            self._pairs({"request_type": "REVISION", "decision": "APPROVED"}),
            {("REVISION", "APPROVED")},
        )

    def test_should_reject_invalid_parameters(self):
        for params, field in (
            ({"request_type": "OTHER"}, "request_type"),
            ({"decision": "MAYBE"}, "decision"),
            ({"date_from": "10/03/2026"}, "date_from"),
            ({"date_from": "2026-03-10", "date_to": "2026-03-09"}, "date_to"),
            ({"page": "0"}, "page"),
            ({"page_size": "101"}, "page_size"),
        ):
            with self.subTest(field=field), self.assertRaises(ActivityQueryError) as context:
                parse_decision_history_query(params)
            self.assertIn(field, context.exception.errors)


class DecisionHistoryPeriodTests(DecisionHistoryFixtureMixin, TestCase):
    def test_should_filter_by_an_inclusive_period(self):
        day = datetime(2026, 3, 10, tzinfo=UTC)
        for moment in (
            day - timedelta(seconds=1),
            day,
            day + timedelta(hours=23, minutes=59, seconds=59),
            day + timedelta(days=1),
        ):
            self._revision_decision(
                self.revision, minutes_ago=(self.now - moment) / timedelta(minutes=1)
            )

        body = self._history({"date_from": "2026-03-10", "date_to": "2026-03-10"})

        self.assertEqual(body["count"], 2)


class DecisionHistoryViewTests(DecisionHistoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("manager-decision-history")
        self._revision_decision(self.revision)

    def test_should_return_the_history_to_a_reviewer(self):
        self.client.force_login(self.manager)

        response = self.client.get(self.url, {"request_type": "REVISION"})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            set(body["results"][0]),
            {
                "id",
                "timestamp",
                "request_type",
                "decision",
                "document",
                "revision",
                "requester",
                "user",
                "reason",
            },
        )

    def test_should_require_authentication_and_a_reviewer_role(self):
        anonymous = self.client.get(self.url)
        self.client.force_login(self.author)
        forbidden = self.client.get(self.url)

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json(), {"error": "AuthenticationRequired"})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"error": "PermissionDenied"})

    def test_should_answer_400_for_invalid_parameters(self):
        self.client.force_login(self.manager)

        response = self.client.get(self.url, {"decision": "MAYBE"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["decision"]["code"], "invalid_choice")
