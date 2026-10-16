from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
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
    ANONYMOUS_NAME,
    NoReplacementManagerError,
    anonymize_user,
    anonymized_email,
    delete_user_account,
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
        self.area.manager = self.manager
        self.area.save()

    def _anonymize(self):
        anonymize_user(self.author)
        self.author.refresh_from_db()

    def test_soft_delete_clears_contact_data_and_deactivates(self):
        self._anonymize()

        self.assertEqual(self.author.name, ANONYMOUS_NAME)
        self.assertEqual(self.author.email, anonymized_email(self.author.pk))
        self.assertFalse(self.author.has_usable_password())
        self.assertIsNone(self.author.terms_accepted_at)
        self.assertFalse(self.author.is_active)
        self.assertTrue(is_anonymized(self.author))
        self.assertTrue(is_identifier_excluded(self.original_email))

    def test_soft_delete_keeps_the_archive_and_authorship(self):
        self._anonymize()

        self.revision.refresh_from_db()
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(File.objects.filter(pk=self.file.pk).count(), 1)
        self.assertEqual(self.revision.author_id, self.author.pk)

    def test_soft_delete_discards_pending_requests_so_they_cannot_be_approved(self):
        summary = anonymize_user(self.author)

        self.assertFalse(DocumentAccess.objects.filter(status=AccessStatus.PENDING).exists())
        self.assertEqual(summary["removed"], {"document_access(pending)": 1})

    def test_soft_delete_hands_manager_work_to_another_manager(self):
        other = User.objects.create_user(
            email="outro.gestor@example.com",
            password="senha-forte-123",
            name="Outro Gestor",
            role=Role.AUDITOR,
            area=self.area,
        )
        pending = Revision.objects.create(
            document=self.document,
            version=2,
            status=RevisionStatus.PENDING,
            change_description="Segunda",
            author=self.author,
            auditor=self.manager,
        )

        anonymize_user(self.manager)

        pending.refresh_from_db()
        self.area.refresh_from_db()
        self.assertEqual(pending.auditor_id, other.pk)
        self.assertEqual(self.area.manager_id, other.pk)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.auditor_id, self.manager.pk)

    def test_soft_delete_is_refused_without_another_manager(self):
        with self.assertRaises(NoReplacementManagerError):
            anonymize_user(self.manager)

        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_other_users_are_left_untouched(self):
        self._anonymize()

        self.manager.refresh_from_db()
        self.assertEqual(self.manager.name, "Gestor")
        self.assertTrue(self.manager.is_active)

    def test_hard_delete_removes_the_user_and_reassigns_relations(self):
        summary = delete_user_account(self.author)

        self.assertFalse(User.objects.filter(pk=self.author.pk).exists())
        self.assertFalse(DocumentAccess.objects.exists())
        self.document.refresh_from_db()
        self.revision.refresh_from_db()
        for value in (
            self.document.created_by_id,
            self.document.responsible_id,
            self.document.updated_by_id,
            self.revision.author_id,
        ):
            self.assertEqual(value, self.manager.pk)
        self.assertEqual(summary["reassigned_to"], self.manager.pk)
        self.assertTrue(is_identifier_excluded(self.original_email))

    def test_hard_delete_of_a_manager_moves_reviews_to_another_manager(self):
        other = User.objects.create_user(
            email="outro.gestor@example.com",
            password="senha-forte-123",
            name="Outro Gestor",
            role=Role.AUDITOR,
            area=self.area,
        )

        delete_user_account(self.manager)

        self.revision.refresh_from_db()
        self.area.refresh_from_db()
        self.assertEqual(self.revision.auditor_id, other.pk)
        self.assertEqual(self.area.manager_id, other.pk)

    def test_hard_delete_is_refused_without_another_manager(self):
        with self.assertRaises(NoReplacementManagerError):
            delete_user_account(self.manager)

        self.assertTrue(User.objects.filter(pk=self.manager.pk).exists())

    def test_deletion_endpoint_anonymizes_and_discards_pending_requests(self):
        client = Client()
        client.force_login(self.author)

        response = client.post("/users/me/request-deletion")

        self.author.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(is_anonymized(self.author))
        self.assertFalse(DocumentAccess.objects.filter(status=AccessStatus.PENDING).exists())
        self.assertEqual(Document.objects.count(), 1)
        audit = AuditLog.objects.get(entity="app_user")
        self.assertEqual(audit.entity_id, self.author.pk)
        self.assertEqual(audit.record["event"], "ACCOUNT_ANONYMIZED")
        self.assertEqual(audit.record["actor"]["name"], "Maria Silva")
