import gzip
import json
import secrets
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    BackupRun,
    Discipline,
    Document,
    DocumentType,
    ErasureKind,
    ExcludedIdentifier,
    Project,
    Role,
    User,
)
from core.services.backup_service import BackupFileError, encrypt, run_backup
from core.services.excluded_identifier_service import (
    identifier_hash,
    store_excluded_identifier,
)
from core.services.user_anonymization_service import (
    ANONYMOUS_NAME,
    anonymize_user,
    anonymized_email,
    delete_user_account,
)
from core.services.user_erasure_reapplication_service import (
    EVENT_ERASURE_REAPPLIED,
    load_register_from_snapshot,
    reapply_user_erasures,
)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class ErasureRegisterTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manager = User.objects.create_user(
            email="gestor@example.com",
            password="Sup3r-secret-pass",
            name="Gestor",
            role=Role.AUDITOR,
            area=self.area,
        )
        self.area.manager = self.manager
        self.area.save()
        self.author = User.objects.create_user(
            email="maria.silva@example.com",
            password="Sup3r-secret-pass",
            name="Maria Silva",
            role=Role.AUTHOR,
            area=self.area,
            terms_accepted_at=timezone.now(),
        )

    def test_should_register_the_kind_of_each_erasure(self):
        viewer = User.objects.create_user(
            email="viewer@example.com", password="x", name="Viewer", area=self.area
        )

        anonymize_user(self.author)
        delete_user_account(viewer)

        kinds = {row.identifier_hash: row.kind for row in ExcludedIdentifier.objects.all()}
        self.assertEqual(kinds[identifier_hash("maria.silva@example.com")], ErasureKind.ANONYMIZED)
        self.assertEqual(kinds[identifier_hash("viewer@example.com")], ErasureKind.DELETED)

    def test_should_keep_deleted_as_the_strongest_kind_of_an_identifier(self):
        store_excluded_identifier("someone@example.com", ErasureKind.ANONYMIZED)

        store_excluded_identifier("someone@example.com", ErasureKind.DELETED)
        store_excluded_identifier("someone@example.com", ErasureKind.ANONYMIZED)

        row = ExcludedIdentifier.objects.get(identifier_hash=identifier_hash("someone@example.com"))
        self.assertEqual(row.kind, ErasureKind.DELETED)
        self.assertEqual(ExcludedIdentifier.objects.count(), 1)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class ReapplyUserErasuresTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manager = User.objects.create_user(
            email="gestor@example.com",
            password="Sup3r-secret-pass",
            name="Gestor",
            role=Role.AUDITOR,
            area=self.area,
        )
        self.area.manager = self.manager
        self.area.save()
        self.author = User.objects.create_user(
            email="maria.silva@example.com",
            password="Sup3r-secret-pass",
            name="Maria Silva",
            role=Role.AUTHOR,
            area=self.area,
            terms_accepted_at=timezone.now(),
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

    def restore_author(self):
        User.objects.filter(pk=self.author.pk).update(
            email="maria.silva@example.com",
            name="Maria Silva",
            is_active=True,
            terms_accepted_at=timezone.now(),
        )
        return User.objects.get(pk=self.author.pk)

    def test_should_anonymize_a_restored_user_registered_as_anonymized(self):
        anonymize_user(self.author)
        self.restore_author()

        summary = reapply_user_erasures()

        self.author.refresh_from_db()
        self.assertEqual(summary, {"anonymized": [self.author.pk], "deleted": [], "failed": []})
        self.assertEqual(self.author.name, ANONYMOUS_NAME)
        self.assertEqual(self.author.email, anonymized_email(self.author.pk))
        self.assertFalse(self.author.is_active)
        self.assertIsNone(self.author.terms_accepted_at)

    def test_should_delete_a_restored_user_registered_as_deleted(self):
        delete_user_account(self.author)
        restored = User.objects.create(
            email="maria.silva@example.com", name="Maria Silva", role=Role.AUTHOR, area=self.area
        )
        Document.objects.filter(pk=self.document.pk).update(
            responsible=restored, created_by=restored, updated_by=restored
        )

        summary = reapply_user_erasures()

        self.document.refresh_from_db()
        self.assertEqual(summary, {"anonymized": [], "deleted": [restored.pk], "failed": []})
        self.assertFalse(User.objects.filter(pk=restored.pk).exists())
        self.assertEqual(self.document.responsible_id, self.manager.pk)
        self.assertEqual(self.document.created_by_id, self.manager.pk)

    def test_should_leave_users_outside_the_register_untouched(self):
        store_excluded_identifier("someone.else@example.com", ErasureKind.DELETED)

        summary = reapply_user_erasures()

        self.author.refresh_from_db()
        self.assertEqual(summary, {"anonymized": [], "deleted": [], "failed": []})
        self.assertEqual(self.author.email, "maria.silva@example.com")
        self.assertTrue(self.author.is_active)
        self.assertEqual(User.objects.count(), 2)

    def test_should_do_nothing_when_the_register_is_empty(self):
        summary = reapply_user_erasures()

        self.assertEqual(summary, {"anonymized": [], "deleted": [], "failed": []})
        self.assertEqual(User.objects.filter(is_active=True).count(), 2)

    def test_should_skip_users_already_anonymized(self):
        anonymize_user(self.author)

        summary = reapply_user_erasures()

        self.assertEqual(summary, {"anonymized": [], "deleted": [], "failed": []})
        self.assertEqual(AuditLog.objects.filter(record__event=EVENT_ERASURE_REAPPLIED).count(), 0)

    def test_should_report_a_restored_user_without_a_replacement_manager(self):
        anonymize_user(self.author)
        self.restore_author()
        User.objects.filter(pk=self.manager.pk).update(is_active=False)

        summary = reapply_user_erasures()

        self.author.refresh_from_db()
        self.assertEqual(summary, {"anonymized": [], "deleted": [], "failed": [self.author.pk]})
        self.assertEqual(self.author.email, "maria.silva@example.com")
        self.assertTrue(self.author.is_active)

    def test_should_write_an_audit_entry_for_each_reapplied_erasure(self):
        anonymize_user(self.author)
        self.restore_author()

        reapply_user_erasures()

        entry = AuditLog.objects.get(record__event=EVENT_ERASURE_REAPPLIED)
        self.assertEqual(entry.action, AuditAction.DELETE)
        self.assertEqual(entry.entity, "app_user")
        self.assertEqual(entry.entity_id, self.author.pk)
        self.assertEqual(entry.record["kind"], ErasureKind.ANONYMIZED)
        self.assertIsNone(entry.user)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class RegisterFromSnapshotTests(TestCase):
    def setUp(self):
        self.backup_dir = Path(tempfile.mkdtemp())
        self.key = secrets.token_hex(32)
        self.overrides = override_settings(
            BACKUP_DIR=self.backup_dir, BACKUP_ENCRYPTION_KEY=self.key
        )
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manager = User.objects.create_user(
            email="gestor@example.com",
            password="Sup3r-secret-pass",
            name="Gestor",
            role=Role.ADMIN,
            area=self.area,
        )

    def encrypted_file(self, payload, name="custom.json.gz.enc"):
        path = self.backup_dir / name
        path.write_bytes(
            encrypt(gzip.compress(json.dumps(payload).encode()), bytes.fromhex(self.key))
        )
        return path

    def test_should_merge_the_register_of_an_encrypted_postgres_snapshot(self):
        store_excluded_identifier("gone@example.com", ErasureKind.DELETED)
        store_excluded_identifier("dismissed@example.com", ErasureKind.ANONYMIZED)
        run = run_backup("POSTGRES")
        ExcludedIdentifier.objects.all().delete()
        store_excluded_identifier("dismissed@example.com", ErasureKind.ANONYMIZED)

        merged = load_register_from_snapshot(Path(run.destination))

        self.assertEqual(merged, 2)
        kinds = {row.identifier_hash: row.kind for row in ExcludedIdentifier.objects.all()}
        self.assertEqual(kinds[identifier_hash("gone@example.com")], ErasureKind.DELETED)
        self.assertEqual(kinds[identifier_hash("dismissed@example.com")], ErasureKind.ANONYMIZED)
        self.assertEqual(len(kinds), 2)

    def test_should_treat_register_entries_without_kind_as_anonymized(self):
        path = self.encrypted_file(
            [
                {
                    "model": "core.excludedidentifier",
                    "pk": 7,
                    "fields": {"identifier_hash": "ab" * 32, "created_at": "2026-11-01T10:00:00Z"},
                },
                {"model": "core.area", "pk": 9, "fields": {"acronym": "QUA", "name": "Qualidade"}},
            ]
        )

        merged = load_register_from_snapshot(path)

        self.assertEqual(merged, 1)
        self.assertEqual(
            ExcludedIdentifier.objects.get(identifier_hash="ab" * 32).kind, "ANONYMIZED"
        )
        self.assertFalse(Area.objects.filter(acronym="QUA").exists())

    def test_should_reject_a_mongodb_snapshot_as_register_source(self):
        path = self.encrypted_file({"database": "api6", "collections": {}})

        with self.assertRaises(BackupFileError):
            load_register_from_snapshot(path)

        self.assertEqual(ExcludedIdentifier.objects.count(), 0)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class ReapplyUserErasuresCommandTests(TestCase):
    def setUp(self):
        self.backup_dir = Path(tempfile.mkdtemp())
        self.key = secrets.token_hex(32)
        self.overrides = override_settings(
            BACKUP_DIR=self.backup_dir, BACKUP_ENCRYPTION_KEY=self.key
        )
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manager = User.objects.create_user(
            email="gestor@example.com",
            password="Sup3r-secret-pass",
            name="Gestor",
            role=Role.ADMIN,
            area=self.area,
        )
        self.author = User.objects.create_user(
            email="maria.silva@example.com",
            password="Sup3r-secret-pass",
            name="Maria Silva",
            role=Role.AUTHOR,
            area=self.area,
        )

    def restore_author(self):
        User.objects.filter(pk=self.author.pk).update(
            email="maria.silva@example.com", name="Maria Silva", is_active=True
        )

    def test_should_print_the_summary_of_the_reapplied_erasures(self):
        anonymize_user(self.author)
        self.restore_author()
        output = StringIO()

        call_command("reapply_user_erasures", stdout=output)

        self.author.refresh_from_db()
        self.assertEqual(output.getvalue().strip(), "Anonymized 1, deleted 0, failed 0.")
        self.assertEqual(self.author.name, ANONYMOUS_NAME)

    def test_should_fail_when_an_erasure_could_not_be_reapplied(self):
        anonymize_user(self.author)
        self.restore_author()
        User.objects.filter(pk=self.manager.pk).update(is_active=False)

        with self.assertRaises(CommandError) as context:
            call_command("reapply_user_erasures", stdout=StringIO())

        self.assertIn(str(self.author.pk), str(context.exception))

    def test_should_merge_the_register_of_the_snapshot_before_reapplying(self):
        anonymize_user(self.author)
        run = run_backup("POSTGRES")
        ExcludedIdentifier.objects.all().delete()
        self.restore_author()
        output = StringIO()

        call_command("reapply_user_erasures", from_snapshot=run.destination, stdout=output)

        self.author.refresh_from_db()
        self.assertEqual(
            output.getvalue().splitlines(),
            ["Register entries merged from the snapshot: 1", "Anonymized 1, deleted 0, failed 0."],
        )
        self.assertEqual(self.author.email, anonymized_email(self.author.pk))
        self.assertEqual(BackupRun.objects.count(), 1)

    def test_should_fail_when_the_snapshot_does_not_exist(self):
        with self.assertRaises(CommandError):
            call_command(
                "reapply_user_erasures",
                from_snapshot=str(self.backup_dir / "missing.json.gz.enc"),
                stdout=StringIO(),
            )

        self.assertTrue(User.objects.get(pk=self.author.pk).is_active)

    def test_should_fail_when_the_snapshot_was_encrypted_with_another_key(self):
        run = run_backup("POSTGRES")

        with override_settings(BACKUP_ENCRYPTION_KEY=secrets.token_hex(32)):
            with self.assertRaises(CommandError) as context:
                call_command(
                    "reapply_user_erasures", from_snapshot=run.destination, stdout=StringIO()
                )

        self.assertIn("InvalidTag", str(context.exception))
