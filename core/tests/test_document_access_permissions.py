import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

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
    DocumentAccessGroup,
    DocumentType,
    Project,
    SecrecyLevel,
    User,
)
from core.services import document_creation_service as service
from core.services.access_group_service import can_user_view_document
from core.services.document_exceptions import DocumentStorageError, DocumentValidationError
from core.services.document_visibility_service import is_visible

PDF_BYTES = b"%PDF-1.4 conditional permissions body"
TEMP_FILE_ID = "aaaaaaaa-3333-4333-8444-666666666666"


@mock.patch("core.services.document_creation_service.get_mongo_db")
class DocumentAccessPermissionsTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, DOCUMENT_STORAGE_DIR=self.storage_dir
        )
        override.enable()
        self.addCleanup(override.disable)

        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.quality = Area.objects.create(acronym="QUA", name="Qualidade")
        self.author = self._user("ana@example.com", self.structures)
        self.inspector = self._user("bia@example.com", self.quality)
        self.stranger = self._user("caio@example.com", self.quality)
        self.former = self._user("dora@example.com", self.quality, active=False)
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.levels = {level.code: level for level in SecrecyLevel.objects.all()}
        self.quality_group = self._group(
            "Qualidade — sigiloso", ConfidentialityLevel.CONFIDENTIAL, members=[self.inspector]
        )
        self.public_group = self._group(
            "Qualidade — público", ConfidentialityLevel.PUBLIC, members=[self.stranger]
        )
        self.retired_group = self._group(
            "Qualidade — antigo", ConfidentialityLevel.SECRET, active=False, members=[self.stranger]
        )
        self.client.force_login(self.author)

    def _user(self, email, area, active=True):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], area=area, is_active=active
        )

    def _group(self, name, level, active=True, members=(), area=None):
        group = AccessGroup.objects.create(
            name=name,
            scope=AccessGroupScope.AREA,
            area=area or self.quality,
            secrecy_level=self.levels[level],
            active=active,
            created_by=self.author,
        )
        for member in members:
            AccessGroupMember.objects.create(group=group, user=member, added_by=self.author)
        return group

    def _temp_file(self):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.pdf"
        path.write_bytes(PDF_BYTES)
        return path

    def _payload(self, confidentiality=ConfidentialityLevel.CONFIDENTIAL, **overrides):
        payload = {
            "temp_file_id": TEMP_FILE_ID,
            "title": "Desenho da caverna 14",
            "description": "Conjunto soldado",
            "project_id": self.project.id,
            "discipline_id": self.discipline.id,
            "document_type": self.document_type.id,
            "confidentiality": confidentiality,
            "responsible_id": self.author.id,
            "areas": ["EST"],
        }
        payload.update(overrides)
        return payload

    def _create(self, **overrides):
        self._temp_file()
        return service.create_document(self._payload(**overrides))

    def _errors(self, **overrides):
        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(self._payload(**overrides))
        return context.exception.errors

    def _post(self, payload):
        return self.client.post(
            reverse("document-list"), data=json.dumps(payload), content_type="application/json"
        )

    def test_should_persist_the_authorized_groups_of_a_confidential_document(self, mongo):
        document = self._create(authorized_group_ids=[self.quality_group.id])

        grants = list(DocumentAccessGroup.objects.filter(document=document))

        self.assertEqual([grant.group for grant in grants], [self.quality_group])
        self.assertEqual(grants[0].granted_by, self.author)
        self.assertIsNotNone(grants[0].granted_at)

    def test_should_persist_several_authorized_groups_once_each(self, mongo):
        other_group = self._group(
            "Estruturas — restrito", ConfidentialityLevel.SECRET, area=self.structures
        )

        document = self._create(
            authorized_group_ids=[self.quality_group.id, other_group.id, self.quality_group.id]
        )

        self.assertEqual(
            set(document.group_grants.values_list("group_id", flat=True)),
            {self.quality_group.id, other_group.id},
        )

    def test_should_accept_a_confidential_document_without_authorized_groups(self, mongo):
        document = self._create(authorized_user_ids=[])

        self.assertEqual(document.confidentiality_level, ConfidentialityLevel.CONFIDENTIAL)
        self.assertFalse(DocumentAccessGroup.objects.exists())
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_reject_a_group_whose_level_is_below_the_document(self, mongo):
        errors = self._errors(authorized_group_ids=[self.quality_group.id, self.public_group.id])

        self.assertEqual(errors["authorized_group_ids"]["code"], "insufficient_level")
        self.assertIn(str(self.public_group.id), errors["authorized_group_ids"]["message"])

    def test_should_reject_unknown_or_inactive_groups(self, mongo):
        errors = self._errors(authorized_group_ids=[self.retired_group.id, 999999])

        self.assertEqual(errors["authorized_group_ids"]["code"], "not_found")

    def test_should_reject_authorized_groups_that_are_not_a_list_of_ids(self, mongo):
        errors = self._errors(authorized_group_ids=[str(self.quality_group.id)])

        self.assertEqual(errors["authorized_group_ids"]["code"], "invalid")

    def test_should_reject_authorized_groups_for_a_public_document(self, mongo):
        errors = self._errors(
            confidentiality=ConfidentialityLevel.PUBLIC,
            authorized_group_ids=[self.quality_group.id],
        )

        self.assertEqual(errors["authorized_group_ids"]["code"], "not_allowed")

    def test_should_reject_authorized_groups_for_a_secret_document(self, mongo):
        errors = self._errors(
            confidentiality=ConfidentialityLevel.SECRET,
            authorized_group_ids=[self.quality_group.id],
            authorized_user_ids=[self.inspector.id],
        )

        self.assertEqual(set(errors), {"authorized_group_ids"})
        self.assertEqual(errors["authorized_group_ids"]["code"], "not_allowed")

    def test_should_require_authorized_users_for_a_secret_document(self, mongo):
        errors = self._errors(confidentiality=ConfidentialityLevel.SECRET)

        self.assertEqual(errors["authorized_user_ids"]["code"], "required")

    def test_should_require_an_authorized_user_other_than_the_responsible(self, mongo):
        errors = self._errors(
            confidentiality=ConfidentialityLevel.SECRET, authorized_user_ids=[self.author.id]
        )

        self.assertEqual(errors["authorized_user_ids"]["code"], "required")

    def test_should_grant_permanent_access_to_the_authorized_users_of_a_secret_document(
        self, mongo
    ):
        document = self._create(
            confidentiality=ConfidentialityLevel.SECRET,
            authorized_user_ids=[self.inspector.id, self.author.id, self.inspector.id],
        )

        accesses = list(DocumentAccess.objects.filter(document=document))

        self.assertEqual([access.user for access in accesses], [self.inspector])
        self.assertEqual(accesses[0].status, AccessStatus.APPROVED)
        self.assertEqual(accesses[0].access_type, AccessType.PERMANENT)
        self.assertEqual(accesses[0].approver, self.author)
        self.assertIsNotNone(accesses[0].decided_at)
        self.assertIsNone(accesses[0].requested_at)
        self.assertIsNone(accesses[0].expires_on)

    def test_should_reject_unknown_or_inactive_authorized_users(self, mongo):
        errors = self._errors(
            confidentiality=ConfidentialityLevel.SECRET,
            authorized_user_ids=[self.inspector.id, self.former.id, 999999],
        )

        self.assertEqual(errors["authorized_user_ids"]["code"], "not_found")
        self.assertIn(str(self.former.id), errors["authorized_user_ids"]["message"])

    def test_should_reject_authorized_users_for_a_confidential_document(self, mongo):
        errors = self._errors(authorized_user_ids=[self.inspector.id])

        self.assertEqual(errors["authorized_user_ids"]["code"], "not_allowed")

    def test_should_reject_authorized_users_that_are_not_a_list_of_ids(self, mongo):
        errors = self._errors(
            confidentiality=ConfidentialityLevel.SECRET, authorized_user_ids=[0, True]
        )

        self.assertEqual(errors["authorized_user_ids"]["code"], "invalid")

    def test_should_not_report_permission_errors_when_the_confidentiality_is_invalid(self, mongo):
        errors = self._errors(confidentiality="TOP", authorized_user_ids=[self.inspector.id])

        self.assertEqual(set(errors), {"confidentiality"})

    def test_should_make_the_document_visible_to_the_members_of_an_authorized_group(self, mongo):
        document = self._create(authorized_group_ids=[self.quality_group.id])

        self.assertTrue(is_visible(document, self.inspector))
        self.assertTrue(can_user_view_document(document, self.inspector))
        self.assertFalse(is_visible(document, self.stranger))
        self.assertFalse(can_user_view_document(document, self.stranger))

    def test_should_hide_the_document_when_the_authorized_group_is_deactivated(self, mongo):
        document = self._create(authorized_group_ids=[self.quality_group.id])

        AccessGroup.objects.filter(pk=self.quality_group.pk).update(active=False)

        self.assertFalse(is_visible(document, self.inspector))
        self.assertFalse(can_user_view_document(document, self.inspector))

    def test_should_make_a_secret_document_visible_to_its_authorized_users(self, mongo):
        document = self._create(
            confidentiality=ConfidentialityLevel.SECRET, authorized_user_ids=[self.inspector.id]
        )

        self.assertTrue(is_visible(document, self.inspector))
        self.assertTrue(can_user_view_document(document, self.inspector))
        self.assertFalse(is_visible(document, self.stranger))

    def test_should_roll_back_the_permissions_when_the_file_cannot_be_stored(self, mongo):
        self._temp_file()
        payload = self._payload(
            confidentiality=ConfidentialityLevel.SECRET, authorized_user_ids=[self.inspector.id]
        )

        with (
            mock.patch("core.services.document_creation_service.shutil.move", side_effect=OSError),
            self.assertRaises(DocumentStorageError),
        ):
            service.create_document(payload)

        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(DocumentAccess.objects.count(), 0)
        self.assertEqual(DocumentAccessGroup.objects.count(), 0)

    def test_should_answer_201_with_the_authorized_groups_of_the_created_document(self, mongo):
        self._temp_file()

        response = self._post(self._payload(authorized_group_ids=[self.quality_group.id]))

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            body["authorized_groups"],
            [{"id": self.quality_group.id, "name": "Qualidade — sigiloso"}],
        )
        self.assertEqual(body["authorized_users"], [])

    def test_should_answer_201_with_the_authorized_users_of_a_secret_document(self, mongo):
        self._temp_file()

        response = self._post(
            self._payload(
                confidentiality=ConfidentialityLevel.SECRET,
                authorized_user_ids=[self.inspector.id],
            )
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["authorized_groups"], [])
        self.assertEqual(
            body["authorized_users"],
            [{"id": self.inspector.id, "name": "bia", "email": "bia@example.com"}],
        )

    def test_should_answer_400_with_the_permission_errors(self, mongo):
        self._temp_file()

        response = self._post(self._payload(confidentiality=ConfidentialityLevel.SECRET))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["authorized_user_ids"]["code"], "required")
        self.assertEqual(Document.objects.count(), 0)
