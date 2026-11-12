import gzip
import json
import secrets
import tempfile
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest import mock

from bson import ObjectId
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from core.models import Area, BackupRun
from core.models.choices import BackupStatus, BackupTarget
from core.services import backup_service
from core.services.backup_service import (
    FILE_MAGIC,
    BackupFileError,
    BackupQueryError,
    decrypt_snapshot,
    list_backup_runs,
    run_backup,
)


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self):
        return iter(self.documents)


class FakeDatabase:
    name = "api6"

    def __init__(self, collections):
        self.collections = collections

    def list_collection_names(self):
        return list(self.collections)

    def __getitem__(self, name):
        return FakeCollection(self.collections[name])


class BackupSnapshotTests(TestCase):
    def setUp(self):
        self.backup_dir = Path(tempfile.mkdtemp())
        self.key = secrets.token_hex(32)
        self.overrides = override_settings(
            BACKUP_DIR=self.backup_dir,
            BACKUP_ENCRYPTION_KEY=self.key,
            BACKUP_KEEP_POSTGRES=2,
            BACKUP_KEEP_MONGODB=1,
        )
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        Area.objects.create(acronym="EST", name="Engenharia Estrutural")

    def _files(self, target):
        folder = self.backup_dir / target.lower()
        return sorted(path.name for path in folder.glob("*")) if folder.exists() else []

    def test_should_write_an_encrypted_postgres_snapshot_and_record_the_run(self):
        run = run_backup(BackupTarget.POSTGRES)

        path = Path(run.destination)
        blob = path.read_bytes()
        decrypted = decrypt_snapshot(path, self.backup_dir / "plain.json")
        rows = json.loads(decrypted.read_text())
        self.assertEqual(run.status, BackupStatus.SUCCEEDED)
        self.assertTrue(run.encrypted)
        self.assertEqual(run.size_bytes, len(blob))
        self.assertEqual(run.sha256, __import__("hashlib").sha256(blob).hexdigest())
        self.assertEqual(run.record_count, len(rows))
        self.assertTrue(blob.startswith(FILE_MAGIC))
        self.assertNotIn(b"core.area", blob)
        self.assertIn("core.area", {row["model"] for row in rows})
        self.assertNotIn("sessions.session", {row["model"] for row in rows})
        self.assertEqual(self._files("POSTGRES"), [path.name])

    def test_should_record_a_failed_run_when_the_key_is_missing(self):
        with override_settings(BACKUP_ENCRYPTION_KEY=""):
            run = run_backup(BackupTarget.POSTGRES)

        self.assertEqual(run.status, BackupStatus.FAILED)
        self.assertEqual(run.error, "BackupConfigurationError")
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(self._files("POSTGRES"), [])

    def test_should_export_every_mongodb_collection_through_the_shared_client(self):
        database = FakeDatabase(
            {
                "temp_uploads": [
                    {"_id": ObjectId(), "original_name": "a.pdf"},
                    {
                        "_id": ObjectId(),
                        "uploaded_at": datetime(2026, 11, 9, tzinfo=UTC),
                    },
                ],
                "document_vectors": [{"_id": ObjectId(), "vector": [0.1, 0.2]}],
            }
        )

        with mock.patch.object(backup_service, "get_mongo_db", return_value=database):
            run = run_backup(BackupTarget.MONGODB)

        payload = json.loads(
            gzip.decompress(
                backup_service.decrypt(Path(run.destination).read_bytes(), bytes.fromhex(self.key))
            )
        )
        self.assertEqual(run.status, BackupStatus.SUCCEEDED)
        self.assertEqual(run.record_count, 3)
        self.assertEqual(sorted(payload["collections"]), ["document_vectors", "temp_uploads"])
        self.assertEqual(payload["collections"]["temp_uploads"][0]["original_name"], "a.pdf")

    def test_should_record_a_failed_mongodb_run_without_leaking_details(self):
        with mock.patch.object(
            backup_service, "get_mongo_db", side_effect=ConnectionError("mongo://secret@host")
        ):
            run = run_backup(BackupTarget.MONGODB)

        self.assertEqual(run.status, BackupStatus.FAILED)
        self.assertEqual(run.error, "ConnectionError")

    def test_should_prune_snapshots_beyond_the_retention_limit(self):
        first = run_backup(BackupTarget.POSTGRES, keep=1)
        second = run_backup(BackupTarget.POSTGRES, keep=1)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.pruned_at)
        self.assertFalse(Path(first.destination).exists())
        self.assertIsNone(second.pruned_at)
        self.assertEqual(self._files("POSTGRES"), [Path(second.destination).name])

    def test_should_run_the_command_and_fail_loudly_when_a_snapshot_fails(self):
        output = StringIO()

        call_command("backup_snapshot", target="postgres", stdout=output)
        with override_settings(BACKUP_ENCRYPTION_KEY=""), self.assertRaises(CommandError):
            call_command("backup_snapshot", target="postgres", stdout=StringIO())

        self.assertIn("POSTGRES: SUCCEEDED", output.getvalue())
        self.assertEqual(
            list(BackupRun.objects.order_by("id").values_list("status", flat=True)),
            [BackupStatus.SUCCEEDED, BackupStatus.FAILED],
        )

    def test_should_decrypt_a_snapshot_with_the_command(self):
        run = run_backup(BackupTarget.POSTGRES)
        output = StringIO()

        call_command("backup_decrypt", run.destination, stdout=output)

        plain = Path(run.destination).with_name(
            Path(run.destination).name.replace(".json.gz.enc", ".json")
        )
        self.assertTrue(plain.exists())
        self.assertIn("core.area", {row["model"] for row in json.loads(plain.read_text())})
        self.assertIn(str(plain), output.getvalue())

    def test_should_reject_a_file_that_is_not_a_snapshot(self):
        bogus = self.backup_dir / "bogus.json.gz.enc"
        bogus.write_bytes(b"not a snapshot")

        with self.assertRaises(BackupFileError):
            decrypt_snapshot(bogus, self.backup_dir / "out.json")
        with self.assertRaises(CommandError):
            call_command("backup_decrypt", str(bogus), stdout=StringIO())

    def test_should_list_runs_by_target(self):
        run_backup(BackupTarget.POSTGRES)
        BackupRun.objects.create(
            target=BackupTarget.MONGODB, status=BackupStatus.FAILED, error="Timeout"
        )

        page = list_backup_runs({"target": "mongodb"}, lambda run: run.target)

        self.assertEqual(page["count"], 1)
        self.assertEqual(page["results"], ["MONGODB"])
        with self.assertRaises(BackupQueryError):
            list_backup_runs({"target": "sqlite", "page": "x"}, lambda run: run.target)
