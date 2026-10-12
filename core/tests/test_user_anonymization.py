from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)
from core.services.excluded_identifier_service import is_identifier_excluded
from core.services.user_anonymization_service import (
    ANONYMIZED_FIELDS,
    ANONYMOUS_NAME,
    anonymize_user,
    anonymized_email,
    is_anonymized,
)


class UserAnonymizationTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.author = User.objects.create_user(
            email="maria.silva@example.com",
            password="Sup3r-secret-pass",
            name="Maria Silva",
            role=Role.AUTHOR,
            area=self.area,
            terms_accepted_at=timezone.now(),
        )
        self.manager = User.objects.create_user(
            email="gestor@example.com",
            password="Sup3r-secret-pass",
            name="Gestor",
            role=Role.AUDITOR,
            area=self.area,
        )
        project = Project.objects.create(code="AK-2100", name="Fuselagem")
        discipline = Discipline.objects.create(code="EST", name="Estruturas")
        document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Documento",
            project=project,
            discipline=discipline,
            document_type=document_type,
            confidentiality_level="PUBLIC",
            responsible=self.author,
            created_by=self.author,
            updated_by=self.author,
        )
        self.document.areas.add(self.area)
        self.revision = Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            change_description="Primeira emissão",
            author=self.author,
            auditor=self.manager,
            audited_at=timezone.now(),
        )
        self.file = File.objects.create(
            revision=self.revision,
            original_name="desenho.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="a" * 64,
            storage_path="AK-2100/v1.pdf",
        )
        self.access = DocumentAccess.objects.create(
            document=self.document,
            user=self.author,
            status=AccessStatus.PENDING,
            justification="Sou a Maria, do ramal 1234",
            requested_at=timezone.now(),
        )
        self.original_email = self.author.email

    def _anonymize(self):
        anonymize_user(self.author, requested_at=timezone.now())
        self.author.refresh_from_db()

    def test_personal_data_is_removed_from_the_user(self):
        self._anonymize()

        self.assertEqual(self.author.name, ANONYMOUS_NAME)
        self.assertEqual(self.author.email, anonymized_email(self.author.pk))
        self.assertNotIn("maria", self.author.email)
        self.assertFalse(self.author.has_usable_password())
        self.assertIsNone(self.author.terms_accepted_at)
        self.assertFalse(self.author.is_active)
        self.assertIsNotNone(self.author.deletion_requested_at)
        self.assertTrue(is_anonymized(self.author))

    def test_documents_revisions_and_files_are_preserved_with_anonymous_authorship(self):
        self._anonymize()

        self.document.refresh_from_db()
        self.revision.refresh_from_db()
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Revision.objects.count(), 1)
        self.assertEqual(File.objects.filter(pk=self.file.pk).count(), 1)
        self.assertEqual(self.document.created_by_id, self.author.pk)
        self.assertEqual(self.document.responsible_id, self.author.pk)
        self.assertEqual(self.document.updated_by_id, self.author.pk)
        self.assertEqual(self.revision.author_id, self.author.pk)
        self.assertEqual(self.document.created_by.name, ANONYMOUS_NAME)
        self.assertEqual(self.revision.author.name, ANONYMOUS_NAME)

    def test_other_users_are_left_untouched(self):
        self._anonymize()

        self.manager.refresh_from_db()
        self.assertEqual(self.manager.name, "Gestor")
        self.assertEqual(self.manager.email, "gestor@example.com")
        self.assertTrue(self.manager.is_active)

    def test_original_email_is_blocked_from_reuse(self):
        self._anonymize()

        self.assertTrue(is_identifier_excluded(self.original_email))

    def test_free_text_written_by_the_user_is_cleared_but_the_access_row_is_kept(self):
        self._anonymize()

        self.access.refresh_from_db()
        self.assertEqual(self.access.justification, "")
        self.assertEqual(self.access.user_id, self.author.pk)

    def test_returns_a_summary_without_personal_data(self):
        summary = anonymize_user(self.author, requested_at=timezone.now())

        self.assertEqual(summary["fields"], list(ANONYMIZED_FIELDS))
        self.assertEqual(summary["cleared"], {"document_access.justification": 1})
        self.assertNotIn("maria", str(summary).lower())

    def test_anonymizing_twice_is_harmless(self):
        self._anonymize()
        self._anonymize()

        self.assertEqual(self.author.email, anonymized_email(self.author.pk))
        self.assertEqual(Document.objects.count(), 1)

    def test_two_anonymized_users_do_not_collide_on_the_unique_email(self):
        other = User.objects.create_user(
            email="outro@example.com",
            password="Sup3r-secret-pass",
            name="Outro",
            area=self.area,
        )

        self._anonymize()
        anonymize_user(other, requested_at=timezone.now())

        self.assertEqual(User.objects.filter(name=ANONYMOUS_NAME).count(), 2)

    def test_deletion_endpoint_anonymizes_and_keeps_the_archive(self):
        client = Client()
        client.force_login(self.author)

        response = client.post("/users/me/request-deletion")

        self.author.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.author.name, ANONYMOUS_NAME)
        self.assertTrue(is_anonymized(self.author))
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Revision.objects.count(), 1)
        audit = AuditLog.objects.get(action=AuditAction.UPDATE, entity="app_user")
        self.assertEqual(audit.entity_id, self.author.pk)
        self.assertEqual(audit.user_id, self.author.pk)
        self.assertNotIn("maria", str(audit.record).lower())
        self.assertEqual(audit.record["event"], "PERSONAL_DATA_DELETION_REQUESTED")
        self.assertIs(audit.record["anonymized"], True)
        self.assertEqual(audit.record["fields"], list(ANONYMIZED_FIELDS))
        self.assertEqual(audit.record["cleared"], {"document_access.justification": 1})
