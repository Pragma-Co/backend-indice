from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentType,
    File,
    FileExtension,
    Project,
    Revision,
    User,
)


class FileExtensionConstraintTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=area
        )
        document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=user,
        )
        self.revision = Revision.objects.create(document=document, version=1, author=user)

    def _file(self, extension, sha_seed):
        return File(
            revision=self.revision,
            original_name=f"file.{extension}",
            extension=extension,
            mime_type="application/octet-stream",
            size_bytes=10,
            sha256=f"{sha_seed:064x}",
            storage_path=f"documents/test/{sha_seed}.{extension}",
        )

    def test_should_accept_every_extension_of_the_enum(self):
        extensions = list(FileExtension.values)

        for index, extension in enumerate(extensions, start=1):
            with self.subTest(extension=extension):
                stored = self._file(extension, index)
                stored.save()

                self.assertIsNotNone(stored.pk)

    def test_should_reject_extensions_removed_from_the_enum(self):
        removed = ["dwg", "dxf", "xls", "xlsx"]

        for index, extension in enumerate(removed, start=100):
            with self.subTest(extension=extension):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self._file(extension, index).save()
