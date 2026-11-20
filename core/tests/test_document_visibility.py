from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.middleware.document_visibility_middleware import DocumentVisibilityMiddleware
from core.models import (
    AccessGroup,
    AccessGroupMember,
    AccessGroupScope,
    AccessStatus,
    AccessType,
    Area,
    ConfidentialityLevel,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Project,
    Role,
    SavedDocument,
    SecrecyLevel,
    User,
)
from core.services.access_group_service import can_user_view_document
from core.services.document_visibility_service import is_visible, visible_documents


def codes(queryset):
    return sorted(queryset.values_list("code", flat=True))


def result_codes(response):
    return sorted(item["code"] for item in response.json()["results"])


class DocumentVisibilityFixtureMixin:
    def setUp(self):
        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manufacturing = Area.objects.create(acronym="MFG", name="Manufatura e Montagem")
        self.author = self._user("author@example.com", Role.AUTHOR, self.structures)
        self.colleague = self._user("colleague@example.com", Role.VIEWER, self.structures)
        self.outsider = self._user("outsider@example.com", Role.VIEWER, self.manufacturing)
        self.manager = self._user("manager@example.com", Role.AUDITOR, self.structures)
        self.fuselage = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.public_document = self._document("AK-2100-EST-DWG-0001", ConfidentialityLevel.PUBLIC)
        self.confidential_document = self._document(
            "AK-2100-EST-DWG-0002", ConfidentialityLevel.CONFIDENTIAL
        )
        self.secret_document = self._document("AK-2100-EST-DWG-0003", ConfidentialityLevel.SECRET)
        self.levels = {level.code: level for level in SecrecyLevel.objects.all()}
        self.client = Client()

    def _user(self, email, role, area, active=True):
        return User.objects.create_user(
            email=email,
            password="secret",
            name=email.split("@")[0],
            role=role,
            area=area,
            is_active=active,
        )

    def _document(self, code, level):
        document = Document.objects.create(
            code=code,
            title=f"Longarina {code}",
            project=self.fuselage,
            discipline=self.discipline,
            document_type=self.document_type,
            confidentiality_level=level,
            responsible=self.author,
            created_by=self.author,
        )
        document.areas.add(self.structures)
        return document

    def _group(self, name, level, area=None, project=None, active=True, members=()):
        group = AccessGroup.objects.create(
            name=name,
            scope=AccessGroupScope.PROJECT if project else AccessGroupScope.AREA,
            area=area,
            project=project,
            secrecy_level=self.levels[level],
            active=active,
            created_by=self.manager,
        )
        for member in members:
            AccessGroupMember.objects.create(group=group, user=member, added_by=self.manager)
        return group

    def _grant(self, document, user):
        return DocumentAccess.objects.create(
            document=document,
            user=user,
            status=AccessStatus.APPROVED,
            access_type=AccessType.PERMANENT,
            approver=self.manager,
            decided_at=timezone.now(),
        )

    def _archive(self, document):
        Document.objects.filter(pk=document.pk).update(
            archived_at=timezone.now(), archived_by=self.manager
        )


class DocumentVisibilityServiceTests(DocumentVisibilityFixtureMixin, TestCase):
    def test_should_show_only_public_documents_to_a_user_of_another_area(self):
        visible = visible_documents(Document.objects.all(), self.outsider)

        self.assertEqual(codes(visible), ["AK-2100-EST-DWG-0001"])

    def test_should_show_public_and_confidential_documents_to_a_user_of_the_area(self):
        visible = visible_documents(Document.objects.all(), self.colleague)

        self.assertEqual(codes(visible), ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0002"])

    def test_should_show_restricted_documents_to_the_responsible_grantees_and_group_members(self):
        grantee = self._user("grantee@example.com", Role.VIEWER, self.manufacturing)
        member = self._user("member@example.com", Role.VIEWER, self.manufacturing)
        self._grant(self.secret_document, grantee)
        self._group(
            "Fuselagem restrito",
            ConfidentialityLevel.SECRET,
            project=self.fuselage,
            members=[member],
        )

        self.assertEqual(len(visible_documents(Document.objects.all(), self.author)), 3)
        self.assertEqual(
            codes(visible_documents(Document.objects.all(), grantee)),
            ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0003"],
        )
        self.assertEqual(len(visible_documents(Document.objects.all(), member)), 3)

    def test_should_hide_everything_from_anonymous_and_inactive_users(self):
        inactive = self._user("inactive@example.com", Role.VIEWER, self.structures, active=False)

        self.assertFalse(visible_documents(Document.objects.all(), None).exists())
        self.assertFalse(visible_documents(Document.objects.all(), inactive).exists())

    def test_should_ignore_inactive_groups_and_groups_below_the_document_level(self):
        inactive_member = self._user("inactive.group@example.com", Role.VIEWER, self.manufacturing)
        lower_member = self._user("lower@example.com", Role.VIEWER, self.manufacturing)
        self._group(
            "Fuselagem restrito",
            ConfidentialityLevel.SECRET,
            project=self.fuselage,
            active=False,
            members=[inactive_member],
        )
        self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[lower_member],
        )

        self.assertEqual(
            codes(visible_documents(Document.objects.all(), inactive_member)),
            ["AK-2100-EST-DWG-0001"],
        )
        self.assertEqual(
            codes(visible_documents(Document.objects.all(), lower_member)),
            ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0002"],
        )

    def test_should_agree_with_the_rule_service_for_every_user_and_document(self):
        grantee = self._user("grantee@example.com", Role.VIEWER, self.manufacturing)
        member = self._user("member@example.com", Role.VIEWER, self.manufacturing)
        self._grant(self.confidential_document, grantee)
        self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[member],
        )
        users = [self.author, self.colleague, self.outsider, self.manager, grantee, member, None]
        documents = [self.public_document, self.confidential_document, self.secret_document]

        decisions = [
            (is_visible(document, user), can_user_view_document(document, user))
            for user in users
            for document in documents
        ]

        self.assertTrue(all(query == rule for query, rule in decisions))
        self.assertEqual(sum(query for query, _ in decisions), 12)


class DocumentVisibilityMiddlewareTests(DocumentVisibilityFixtureMixin, TestCase):
    def _request(self, user, path="/documents", **params):
        request = RequestFactory().get(path, params)
        request.user = user
        DocumentVisibilityMiddleware(lambda req: req)(request)
        return request

    def test_should_resolve_the_active_session_user_as_the_viewer(self):
        request = self._request(self.colleague)

        self.assertEqual(request.viewer, self.colleague)

    def test_should_resolve_no_viewer_for_anonymous_and_inactive_users(self):
        inactive = self._user("inactive@example.com", Role.VIEWER, self.structures, active=False)

        self.assertIsNone(self._request(AnonymousUser()).viewer)
        self.assertIsNone(self._request(inactive).viewer)

    def test_should_accept_the_user_id_fallback_only_while_debug_is_on(self):
        with override_settings(DEBUG=True):
            debug_request = self._request(AnonymousUser(), user_id=self.colleague.id)
        with override_settings(DEBUG=False):
            production_request = self._request(AnonymousUser(), user_id=self.colleague.id)

        self.assertEqual(debug_request.viewer, self.colleague)
        self.assertIsNone(production_request.viewer)


class DocumentVisibilityRouteTests(DocumentVisibilityFixtureMixin, TestCase):
    def test_should_hide_restricted_documents_from_the_listing(self):
        self.client.force_login(self.outsider)
        outsider_response = self.client.get(reverse("document-list"))
        self.client.force_login(self.colleague)
        colleague_response = self.client.get(reverse("document-list"))

        self.assertEqual(result_codes(outsider_response), ["AK-2100-EST-DWG-0001"])
        self.assertEqual(outsider_response.json()["count"], 1)
        self.assertEqual(
            result_codes(colleague_response), ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0002"]
        )

    def test_should_hide_restricted_documents_from_the_search(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("document-search"), {"q": "longarina"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(result_codes(response), ["AK-2100-EST-DWG-0001"])

    def test_should_answer_404_for_the_detail_of_a_hidden_document(self):
        self.client.force_login(self.outsider)

        hidden = self.client.get(reverse("document-detail", args=[self.secret_document.id]))
        shown = self.client.get(reverse("document-detail", args=[self.public_document.id]))

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json(), {"error": "DocumentNotFound"})
        self.assertEqual(shown.status_code, 200)
        self.assertEqual(shown.json()["code"], "AK-2100-EST-DWG-0001")

    def test_should_show_a_restricted_document_after_a_grant_or_a_group_membership(self):
        grantee = self._user("grantee@example.com", Role.VIEWER, self.manufacturing)
        member = self._user("member@example.com", Role.VIEWER, self.manufacturing)
        self._grant(self.secret_document, grantee)
        self._group(
            "Fuselagem restrito",
            ConfidentialityLevel.SECRET,
            project=self.fuselage,
            members=[member],
        )
        self.client.force_login(grantee)
        grantee_detail = self.client.get(reverse("document-detail", args=[self.secret_document.id]))
        self.client.force_login(member)
        member_listing = self.client.get(reverse("document-list"))

        self.assertEqual(grantee_detail.status_code, 200)
        self.assertEqual(grantee_detail.json()["access_status"], "APPROVED")
        self.assertEqual(
            result_codes(member_listing),
            ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0002", "AK-2100-EST-DWG-0003"],
        )

    def test_should_hide_restricted_documents_from_the_recommendations(self):
        self.client.force_login(self.outsider)
        url = reverse("document-recommendations", args=[self.public_document.id])

        outsider_response = self.client.get(url)
        hidden_base = self.client.get(
            reverse("document-recommendations", args=[self.secret_document.id])
        )
        self.client.force_login(self.colleague)
        colleague_response = self.client.get(url)

        project_items = lambda response: [  # noqa: E731
            item["code"]
            for collection in response.json()["collections"]
            if collection["key"] == "project"
            for item in collection["items"]
        ]
        self.assertEqual(project_items(outsider_response), [])
        self.assertEqual(hidden_base.status_code, 404)
        self.assertEqual(project_items(colleague_response), ["AK-2100-EST-DWG-0002"])

    def test_should_hide_archived_restricted_documents_from_the_manager_list(self):
        self._archive(self.confidential_document)
        self._archive(self.secret_document)
        self.client.force_login(self.manager)

        response = self.client.get(reverse("document-archived-list"))

        self.assertEqual(result_codes(response), ["AK-2100-EST-DWG-0002"])

    def test_should_hide_saved_documents_the_user_cannot_see(self):
        SavedDocument.objects.create(user=self.outsider, document=self.secret_document)
        SavedDocument.objects.create(user=self.outsider, document=self.public_document)
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("personal-library"))

        self.assertEqual(result_codes(response), ["AK-2100-EST-DWG-0001"])

    def test_should_require_a_session_on_the_query_routes(self):
        anonymous = Client()

        responses = [
            anonymous.get(reverse("document-list")),
            anonymous.get(reverse("document-search"), {"q": "longarina"}),
            anonymous.get(reverse("document-detail", args=[self.public_document.id])),
            anonymous.get(reverse("document-recommendations", args=[self.public_document.id])),
        ]

        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401])
        self.assertEqual(responses[0].json(), {"error": "AuthenticationRequired"})
