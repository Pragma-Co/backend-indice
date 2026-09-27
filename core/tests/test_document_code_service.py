from django.test import TestCase

from core.models import Discipline, Document, DocumentType, Project, User
from core.models.organization import Area
from core.services.document_code_service import (
    build_code_prefix,
    build_document_code,
    next_sequence,
)


class BuildDocumentCodeTests(TestCase):
    def test_should_join_catalog_codes_and_zero_padded_sequence(self):
        project = Project(code="AK-2100")
        discipline = Discipline(code="EST")
        document_type = DocumentType(code="DWG")

        prefix = build_code_prefix(project, discipline, document_type)
        code = build_document_code(prefix, 7)

        self.assertEqual(prefix, "AK-2100-EST-DWG")
        self.assertEqual(code, "AK-2100-EST-DWG-0007")

    def test_should_upper_case_the_prefix(self):
        prefix = build_code_prefix(
            Project(code="ak-1"), Discipline(code="est"), DocumentType(code="dwg")
        )

        self.assertEqual(prefix, "AK-1-EST-DWG")

    def test_should_widen_the_sequence_beyond_four_digits(self):
        code = build_document_code("AK-2100-EST-DWG", 12345)

        self.assertEqual(code, "AK-2100-EST-DWG-12345")


class NextSequenceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.prefix = "AK-2100-EST-DWG"

    def _document(self, code):
        return Document.objects.create(
            code=code,
            title=code,
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_should_start_at_one_when_no_document_shares_the_prefix(self):
        sequence = next_sequence(self.prefix)

        self.assertEqual(sequence, 1)

    def test_should_return_highest_sequence_plus_one(self):
        self._document("AK-2100-EST-DWG-0001")
        self._document("AK-2100-EST-DWG-0007")
        self._document("AK-2100-EST-DWG-0003")

        sequence = next_sequence(self.prefix)

        self.assertEqual(sequence, 8)

    def test_should_ignore_documents_with_a_different_prefix(self):
        self._document("AK-2100-EST-DWG-0004")
        self._document("AK-2100-EST-MEM-0009")
        self._document("AK-2100-EST-DWGX-0009")

        sequence = next_sequence(self.prefix)

        self.assertEqual(sequence, 5)
