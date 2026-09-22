from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Project,
    Revision,
    RevisionStatus,
    User,
)
from core.models.choices import AccessStatus
from core.services.documents_exceptions import (
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.documents_service import (
    build_simple_filters,
    get_document_detail,
    request_document_access,
)


class DocumentsViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.project.disciplines.add(self.discipline)
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.user = User.objects.create_user(
            email="user@example.com",
            password="test-password",
            name="User",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-001",
            title="Relatório de engenharia",
            description="Memorial descritivo",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
            created_at=timezone.now() - timedelta(days=2),
            updated_at=timezone.now() - timedelta(days=1),
        )
        self.document.areas.add(self.area)
        self.client = Client()

    def test_returns_all_active_documents_without_filters(self):
        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["code"], "DOC-001")

    def test_filters_documents_by_query_and_area(self):
        response = self.client.get("/documents", {"q": "memorial", "area": "ENG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()["results"]], ["DOC-001"])

    def test_returns_empty_list_when_filter_does_not_match(self):
        response = self.client.get("/documents", {"tipo": "DWG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"count": 0, "total_pages": 1, "current_page": 1, "page_size": 20, "results": []},
        )

    def _other_document(self, code):
        document = Document.objects.create(
            code=code,
            title=code,
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
        )
        document.areas.add(self.area)
        return document

    def test_should_return_null_status_for_a_document_without_revisions(self):
        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["results"][0]["status"])

    def test_should_return_the_status_of_the_only_revision(self):
        Revision.objects.create(document=self.document, version=1, author=self.user)

        response = self.client.get("/documents")

        self.assertEqual(response.json()["results"][0]["status"], "PENDING")

    def test_should_return_the_status_of_the_most_recent_revision(self):
        auditor = User.objects.create_user(
            email="auditor@example.com", password="test-password", name="Auditor", area=self.area
        )
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.user,
            auditor=auditor,
            audited_at=timezone.now(),
        )
        Revision.objects.create(
            document=self.document, version=2, status=RevisionStatus.PENDING, author=self.user
        )

        response = self.client.get("/documents")

        self.assertEqual(response.json()["results"][0]["status"], "PENDING")

    def test_should_keep_the_status_when_filters_are_applied(self):
        Revision.objects.create(document=self.document, version=1, author=self.user)

        response = self.client.get("/documents", {"q": "memorial", "area": "ENG"})

        self.assertEqual(
            [(item["code"], item["status"]) for item in response.json()["results"]],
            [("DOC-001", "PENDING")],
        )

    def test_should_not_run_one_status_query_per_document(self):
        for index in range(4):
            document = self._other_document(f"DOC-10{index}")
            Revision.objects.create(document=document, version=1, author=self.user)

        with self.assertNumQueries(4):
            response = self.client.get("/documents")

        self.assertEqual(len(response.json()["results"]), 5)


class DocumentsSearchAndPaginationTests(TestCase):
    def setUp(self):
        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.quality = Area.objects.create(acronym="QUA", name="Qualidade")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.drawing = DocumentType.objects.create(code="DWG", name="Desenho Técnico")
        self.report = DocumentType.objects.create(code="MEM", name="Memorial de Cálculo")
        self.user = User.objects.create_user(
            email="ana@example.com", password="test-password", name="Ana", area=self.structures
        )
        self.client = Client()

    def _document(self, code, title, document_type=None, area=None, days_ago=0):
        moment = timezone.now() - timedelta(days=days_ago)
        document = Document.objects.create(
            code=code,
            title=title,
            project=self.project,
            discipline=self.discipline,
            document_type=document_type or self.drawing,
            responsible=self.user,
            created_at=moment,
            updated_at=moment,
        )
        document.areas.add(area or self.structures)
        return document

    def _codes(self, response):
        return [item["code"] for item in response.json()["results"]]

    def test_should_return_every_document_with_pagination_metadata_without_parameters(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho da caverna 14", days_ago=3)
        self._document("AK-2100-EST-MEM-0001", "Memorial da longarina", self.report, days_ago=2)
        self._document("AK-2100-EST-DWG-0002", "Desenho do revestimento", days_ago=1)

        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["total_pages"], 1)
        self.assertEqual(body["current_page"], 1)
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(len(body["results"]), 3)

    def test_should_return_the_columns_the_results_table_needs(self):
        document = self._document("AK-2100-EST-DWG-0001", "Desenho da caverna 14")
        Revision.objects.create(document=document, version=1, author=self.user)
        Revision.objects.create(document=document, version=2, author=self.user)

        response = self.client.get("/documents")

        item = response.json()["results"][0]
        self.assertEqual(item["code"], "AK-2100-EST-DWG-0001")
        self.assertEqual(item["title"], "Desenho da caverna 14")
        self.assertEqual(item["type"], {"code": "DWG", "name": "Desenho Técnico"})
        self.assertEqual(item["discipline"], {"code": "EST", "name": "Estruturas"})
        self.assertEqual(item["revision"], {"version": 2, "label": "REV02"})
        self.assertEqual(item["status"], "PENDING")
        self.assertIn("updated_at", item)

    def test_should_return_null_revision_for_a_document_without_revisions(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho da caverna 14")

        response = self.client.get("/documents")

        self.assertIsNone(response.json()["results"][0]["revision"])

    def test_should_order_the_most_recent_documents_first(self):
        self._document("OLD", "Antigo", days_ago=30)
        self._document("NEW", "Novo", days_ago=0)
        self._document("MID", "Intermediário", days_ago=10)

        response = self.client.get("/documents")

        self.assertEqual(self._codes(response), ["NEW", "MID", "OLD"])

    def test_should_search_the_code_ignoring_case(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho da caverna 14")
        self._document("AK-2100-EST-MEM-0001", "Memorial da longarina", self.report)

        response = self.client.get("/documents", {"q": "est-mem"})

        self.assertEqual(self._codes(response), ["AK-2100-EST-MEM-0001"])
        self.assertEqual(response.json()["count"], 1)

    def test_should_search_the_title_ignoring_case(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho da Caverna 14")
        self._document("AK-2100-EST-MEM-0001", "Memorial da longarina", self.report)

        response = self.client.get("/documents", {"q": "CAVERNA"})

        self.assertEqual(self._codes(response), ["AK-2100-EST-DWG-0001"])

    def test_should_combine_search_type_area_and_date_filters(self):
        self._document("MATCH", "Desenho da caverna 14", self.drawing, self.structures, days_ago=2)
        self._document("OTHER-TYPE", "Desenho da caverna 15", self.report, self.structures, 2)
        self._document("OTHER-AREA", "Desenho da caverna 16", self.drawing, self.quality, 2)
        self._document("TOO-OLD", "Desenho da caverna 17", self.drawing, self.structures, 20)
        self._document("OTHER-TITLE", "Revestimento", self.drawing, self.structures, 2)

        response = self.client.get(
            "/documents", {"q": "caverna", "tipo": "DWG", "area": "EST", "data": "last_7_days"}
        )

        self.assertEqual(self._codes(response), ["MATCH"])
        self.assertEqual(response.json()["count"], 1)

    def test_should_filter_by_an_explicit_date_range(self):
        self._document("INSIDE", "Dentro", days_ago=5)
        self._document("BEFORE", "Antes", days_ago=15)
        self._document("AFTER", "Depois", days_ago=0)
        date_from = (timezone.now() - timedelta(days=7)).date().isoformat()
        date_to = (timezone.now() - timedelta(days=3)).date().isoformat()

        response = self.client.get("/documents", {"date_from": date_from, "date_to": date_to})

        self.assertEqual(self._codes(response), ["INSIDE"])

    def test_should_not_repeat_a_document_matched_through_several_tags(self):
        document = self._document("AK-2100-EST-DWG-0001", "Desenho")
        document.tags.create(name="caverna 14")
        document.tags.create(name="caverna dianteira")

        response = self.client.get("/documents", {"q": "caverna"})

        self.assertEqual(self._codes(response), ["AK-2100-EST-DWG-0001"])
        self.assertEqual(response.json()["count"], 1)

    def test_should_navigate_through_the_pages_without_overlap(self):
        for index in range(5):
            self._document(f"DOC-{index}", f"Documento {index}", days_ago=index)

        first = self.client.get("/documents", {"page_size": 2})
        second = self.client.get("/documents", {"page_size": 2, "page": 2})
        third = self.client.get("/documents", {"page_size": 2, "page": 3})

        self.assertEqual(self._codes(first), ["DOC-0", "DOC-1"])
        self.assertEqual(self._codes(second), ["DOC-2", "DOC-3"])
        self.assertEqual(self._codes(third), ["DOC-4"])
        for page_number, response in enumerate((first, second, third), start=1):
            self.assertEqual(response.json()["count"], 5)
            self.assertEqual(response.json()["total_pages"], 3)
            self.assertEqual(response.json()["current_page"], page_number)

    def test_should_keep_the_filters_while_paginating(self):
        for index in range(3):
            self._document(f"DWG-{index}", f"Desenho {index}", self.drawing, days_ago=index)
        self._document("MEM-0", "Memorial", self.report)

        response = self.client.get("/documents", {"tipo": "DWG", "page_size": 2, "page": 2})

        self.assertEqual(self._codes(response), ["DWG-2"])
        self.assertEqual(response.json()["count"], 3)
        self.assertEqual(response.json()["total_pages"], 2)

    def test_should_return_an_empty_page_beyond_the_last_one(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho")

        response = self.client.get("/documents", {"page": 9})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["total_pages"], 1)
        self.assertEqual(response.json()["current_page"], 9)

    def test_should_use_twenty_items_per_page_by_default(self):
        for index in range(25):
            self._document(f"DOC-{index:02d}", f"Documento {index}", days_ago=index)

        response = self.client.get("/documents")

        self.assertEqual(len(response.json()["results"]), 20)
        self.assertEqual(response.json()["total_pages"], 2)

    def test_should_cap_the_page_size(self):
        self._document("AK-2100-EST-DWG-0001", "Desenho")

        response = self.client.get("/documents", {"page_size": 5000})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page_size"], 100)

    def test_should_answer_400_with_a_code_per_invalid_pagination_parameter(self):
        response = self.client.get("/documents", {"page": "abc", "page_size": "0"})

        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(errors["page"]["code"], "invalid")
        self.assertEqual(errors["page_size"]["code"], "invalid")

    def test_should_answer_400_for_invalid_date_filters(self):
        response = self.client.get(
            "/documents", {"data": "yesterday", "date_from": "2026-13-45", "date_to": "soon"}
        )

        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(errors["data"]["code"], "invalid_choice")
        self.assertEqual(errors["date_from"]["code"], "invalid")
        self.assertEqual(errors["date_to"]["code"], "invalid")

    def test_should_run_a_fixed_number_of_queries_per_page(self):
        for index in range(12):
            self._document(f"DOC-{index:02d}", f"Documento {index}", days_ago=index)

        with self.assertNumQueries(4):
            response = self.client.get("/documents", {"page_size": 10})

        self.assertEqual(len(response.json()["results"]), 10)


class DocumentsAdvancedFiltersTests(TestCase):
    def setUp(self):
        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.quality = Area.objects.create(acronym="QUA", name="Qualidade")
        self.systems = Area.objects.create(acronym="SIS", name="Sistemas")
        self.structural = Discipline.objects.create(code="EST", name="Estruturas")
        self.materials = Discipline.objects.create(code="MAT", name="Materiais")
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.drawing = DocumentType.objects.create(code="DWG", name="Desenho Técnico")
        self.report = DocumentType.objects.create(code="MEM", name="Memorial de Cálculo")
        self.spec = DocumentType.objects.create(code="ESP", name="Especificação")
        self.ana = User.objects.create_user(
            email="ana@example.com", password="test-password", name="Ana", area=self.structures
        )
        self.bruno = User.objects.create_user(
            email="bruno@example.com", password="test-password", name="Bruno", area=self.quality
        )
        self.client = Client()

    def _document(
        self,
        code,
        document_type=None,
        areas=None,
        discipline=None,
        responsible=None,
        days_ago=0,
        status=None,
        tags=(),
        title=None,
        description="",
    ):
        moment = timezone.now() - timedelta(days=days_ago)
        document = Document.objects.create(
            code=code,
            title=title or code,
            description=description,
            project=self.project,
            discipline=discipline or self.structural,
            document_type=document_type or self.drawing,
            responsible=responsible or self.ana,
            created_at=moment,
            updated_at=moment,
        )
        document.areas.add(*(areas or [self.structures]))
        for name in tags:
            document.tags.create(name=name)
        if status is not None:
            self._revision(document, 1, status)
        return document

    def _revision(self, document, version, status):
        decided = status != RevisionStatus.PENDING
        return Revision.objects.create(
            document=document,
            version=version,
            status=status,
            author=self.ana,
            auditor=self.bruno if decided else None,
            audited_at=timezone.now() if decided else None,
        )

    def _codes(self, response):
        return sorted(item["code"] for item in response.json()["results"])

    def test_should_accept_several_types_as_a_repeated_parameter(self):
        self._document("DWG-1", self.drawing)
        self._document("MEM-1", self.report)
        self._document("ESP-1", self.spec)

        response = self.client.get("/documents?tipo=DWG&tipo=MEM")

        self.assertEqual(self._codes(response), ["DWG-1", "MEM-1"])
        self.assertEqual(response.json()["count"], 2)

    def test_should_accept_comma_separated_bracketed_and_lower_case_values(self):
        self._document("DWG-1", self.drawing)
        self._document("MEM-1", self.report)
        self._document("ESP-1", self.spec)

        comma = self.client.get("/documents", {"tipo": "dwg, mem"})
        brackets = self.client.get("/documents?tipo[]=DWG&tipo[]=ESP")

        self.assertEqual(self._codes(comma), ["DWG-1", "MEM-1"])
        self.assertEqual(self._codes(brackets), ["DWG-1", "ESP-1"])

    def test_should_match_any_of_several_areas_without_repeating_documents(self):
        self._document("BOTH", areas=[self.structures, self.quality])
        self._document("QUALITY", areas=[self.quality])
        self._document("SYSTEMS", areas=[self.systems])

        response = self.client.get("/documents", {"area": "EST,QUA"})

        self.assertEqual(self._codes(response), ["BOTH", "QUALITY"])
        self.assertEqual(response.json()["count"], 2)

    def test_should_filter_by_several_disciplines(self):
        self._document("STRUCTURAL", discipline=self.structural)
        self._document("MATERIALS", discipline=self.materials)

        one = self.client.get("/documents", {"discipline": "MAT"})
        both = self.client.get("/documents?discipline=MAT&discipline=EST")

        self.assertEqual(self._codes(one), ["MATERIALS"])
        self.assertEqual(self._codes(both), ["MATERIALS", "STRUCTURAL"])

    def test_should_filter_by_the_status_of_the_most_recent_revision(self):
        revised = self._document("REVISED", status=RevisionStatus.APPROVED)
        self._revision(revised, 2, RevisionStatus.PENDING)
        self._document("APPROVED", status=RevisionStatus.APPROVED)
        self._document("OBSOLETE", status=RevisionStatus.OBSOLETE)
        self._document("NO-REVISION")

        pending = self.client.get("/documents", {"status": "PENDING"})
        several = self.client.get("/documents?status=APPROVED&status=OBSOLETE")

        self.assertEqual(self._codes(pending), ["REVISED"])
        self.assertEqual(self._codes(several), ["APPROVED", "OBSOLETE"])

    def test_should_answer_400_for_an_unknown_status(self):
        response = self.client.get("/documents", {"status": "PENDING,DRAFT"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["status"]["code"], "invalid_choice")

    def test_should_filter_by_the_responsible_user(self):
        self._document("FROM-ANA", responsible=self.ana)
        self._document("FROM-BRUNO", responsible=self.bruno)

        response = self.client.get("/documents", {"responsible_id": self.bruno.id})
        nobody = self.client.get("/documents", {"responsible_id": 999999})

        self.assertEqual(self._codes(response), ["FROM-BRUNO"])
        self.assertEqual(nobody.json()["count"], 0)

    def test_should_answer_400_for_an_invalid_responsible_id(self):
        response = self.client.get("/documents", {"responsible_id": "ana"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["responsible_id"]["code"], "invalid")

    def test_should_filter_by_any_of_several_tags_ignoring_case(self):
        self._document("CAVERNA", tags=["Caverna 14"])
        self._document("LONGARINA", tags=["longarina"])
        self._document("UNTAGGED")

        response = self.client.get("/documents", {"tags": "caverna 14,LONGARINA"})

        self.assertEqual(self._codes(response), ["CAVERNA", "LONGARINA"])

    def test_should_search_the_description_and_the_tags_too(self):
        self._document("BY-DESCRIPTION", description="Conjunto soldado da caverna")
        self._document("BY-TAG", tags=["caverna dianteira"])
        self._document("BY-TITLE", title="Desenho da Caverna 14")
        self._document("UNRELATED", title="Revestimento")

        response = self.client.get("/documents", {"q": "caverna"})

        self.assertEqual(self._codes(response), ["BY-DESCRIPTION", "BY-TAG", "BY-TITLE"])
        self.assertEqual(response.json()["count"], 3)

    def test_should_combine_status_area_type_and_date_filters(self):
        self._document(
            "MATCH", self.drawing, [self.quality], status=RevisionStatus.APPROVED, days_ago=3
        )
        self._document(
            "WRONG-STATUS", self.drawing, [self.quality], status=RevisionStatus.PENDING, days_ago=3
        )
        self._document(
            "WRONG-AREA", self.drawing, [self.systems], status=RevisionStatus.APPROVED, days_ago=3
        )
        self._document(
            "WRONG-TYPE", self.spec, [self.quality], status=RevisionStatus.APPROVED, days_ago=3
        )
        self._document(
            "TOO-OLD", self.drawing, [self.quality], status=RevisionStatus.APPROVED, days_ago=40
        )
        date_from = (timezone.now() - timedelta(days=7)).date().isoformat()

        response = self.client.get(
            "/documents",
            {"status": "APPROVED", "area": "QUA,EST", "tipo": "DWG,MEM", "date_from": date_from},
        )

        self.assertEqual(self._codes(response), ["MATCH"])
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["total_pages"], 1)

    def test_should_return_nothing_for_a_date_range_without_documents(self):
        self._document("RECENT", days_ago=1)

        response = self.client.get(
            "/documents", {"date_from": "2020-01-01", "date_to": "2020-12-31"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response.json()["count"], 0)

    def test_should_include_both_ends_of_the_date_range(self):
        self._document("ON-START", days_ago=6)
        self._document("ON-END", days_ago=2)
        self._document("DAY-BEFORE", days_ago=7)
        self._document("DAY-AFTER", days_ago=1)
        start = (timezone.now() - timedelta(days=6)).date().isoformat()
        end = (timezone.now() - timedelta(days=2)).date().isoformat()

        response = self.client.get("/documents", {"date_from": start, "date_to": end})

        self.assertEqual(self._codes(response), ["ON-END", "ON-START"])

    def test_should_accept_the_portuguese_names_of_the_date_range(self):
        self._document("INSIDE", days_ago=5)
        self._document("OUTSIDE", days_ago=30)
        start = (timezone.now() - timedelta(days=7)).date().isoformat()
        end = (timezone.now() - timedelta(days=3)).date().isoformat()

        response = self.client.get("/documents", {"data_inicio": start, "data_fim": end})

        self.assertEqual(self._codes(response), ["INSIDE"])

    def test_should_answer_400_for_an_inverted_or_malformed_date_range(self):
        inverted = self.client.get(
            "/documents", {"date_from": "2026-09-10", "date_to": "2026-09-01"}
        )
        malformed = self.client.get("/documents", {"data_inicio": "10/09/2026"})

        self.assertEqual(inverted.status_code, 400)
        self.assertEqual(inverted.json()["errors"]["date_to"]["code"], "invalid_range")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["errors"]["data_inicio"]["code"], "invalid")

    def test_should_paginate_only_the_documents_that_match_every_filter(self):
        for index in range(5):
            self._document(
                f"DWG-{index}", self.drawing, status=RevisionStatus.PENDING, days_ago=index
            )
        for index in range(4):
            self._document(f"MEM-{index}", self.report, status=RevisionStatus.PENDING)
        self._document("DWG-APPROVED", self.drawing, status=RevisionStatus.APPROVED)

        response = self.client.get(
            "/documents", {"tipo": "DWG", "status": "PENDING", "page_size": 2, "page": 3}
        )

        self.assertEqual(response.json()["count"], 5)
        self.assertEqual(response.json()["total_pages"], 3)
        self.assertEqual(response.json()["current_page"], 3)
        self.assertEqual(self._codes(response), ["DWG-4"])

    def test_should_keep_a_fixed_number_of_queries_with_every_filter_active(self):
        for index in range(8):
            self._document(
                f"DOC-{index}",
                self.drawing,
                [self.structures, self.quality],
                status=RevisionStatus.PENDING,
                tags=[f"tag-{index}", "comum"] if index == 0 else [f"tag-{index}"],
                description="caverna",
            )

        with self.assertNumQueries(4):
            response = self.client.get(
                "/documents",
                {
                    "q": "caverna",
                    "tipo": "DWG,MEM",
                    "area": "EST,QUA",
                    "discipline": "EST",
                    "status": "PENDING,APPROVED",
                    "responsible_id": self.ana.id,
                    "data": "last_7_days",
                },
            )

        self.assertEqual(response.json()["count"], 8)


class SimpleFiltersViewTests(TestCase):
    def setUp(self):
        cache.clear()
        Area.objects.create(acronym="ENG", name="Engenharia", active=True)
        Area.objects.create(acronym="OLD", name="Desativada", active=False)
        DocumentType.objects.create(code="PDF", name="Relatório", active=True)
        DocumentType.objects.create(code="OLD", name="Desativado", active=False)
        self.client = Client()

    def test_returns_active_filter_groups(self):
        response = self.client.get("/documents/simple-filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()), {"areas", "types", "disciplines", "statuses", "dates"}
        )
        self.assertEqual(response.json()["areas"], [{"acronym": "ENG", "name": "Engenharia"}])
        self.assertEqual(response.json()["types"], [{"code": "PDF", "name": "Relatório"}])
        self.assertTrue(response.json()["dates"])

    @mock.patch("core.services.documents_service.cache")
    def test_uses_cached_filter_groups(self, mocked_cache):
        mocked_cache.get.return_value = {"areas": [], "types": [], "dates": []}

        response = self.client.get("/documents/simple-filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"areas": [], "types": [], "dates": []})
        mocked_cache.set.assert_not_called()

    def test_builds_filter_groups_with_expected_shape(self):
        self.assertEqual(
            set(build_simple_filters()), {"areas", "types", "disciplines", "statuses", "dates"}
        )

    def test_should_offer_active_disciplines_and_every_revision_status(self):
        Discipline.objects.create(code="EST", name="Estruturas")
        Discipline.objects.create(code="PNE", name="Pneumáticos", active=False)

        filters = build_simple_filters()

        self.assertEqual(filters["disciplines"], [{"code": "EST", "name": "Estruturas"}])
        self.assertEqual(
            [status["value"] for status in filters["statuses"]],
            ["PENDING", "APPROVED", "REJECTED", "OBSOLETE"],
        )
        self.assertEqual(filters["statuses"][0]["label"], "Em revisão")


class DocumentDetailServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="test-password",
            name="Other",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-100",
            title="Relatório de engenharia",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        self.document.areas.add(self.area)
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.responsible,
            auditor=self.responsible,
            audited_at=timezone.now(),
        )

    def test_should_return_document_not_found_for_missing_id(self):
        with self.assertRaises(DocumentNotFoundError):
            get_document_detail(999999)

    def test_should_return_document_not_found_when_type_is_inactive(self):
        self.document_type.active = False
        self.document_type.save()

        with self.assertRaises(DocumentNotFoundError):
            get_document_detail(self.document.id)

    def test_should_return_pending_access_when_no_user_is_given(self):
        detail = get_document_detail(self.document.id)

        self.assertEqual(detail["access_status"], "PENDING")

    def test_should_return_approved_access_for_the_document_responsible(self):
        detail = get_document_detail(self.document.id, user_id=self.responsible.id)

        self.assertEqual(detail["access_status"], "APPROVED")

    def test_should_return_approved_access_when_user_has_a_grant(self):
        DocumentAccess.objects.create(
            document=self.document,
            user=self.other_user,
            status=AccessStatus.APPROVED,
            approver=self.responsible,
            decided_at=timezone.now(),
        )

        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "APPROVED")

    def test_should_return_pending_access_for_a_user_without_grant(self):
        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "PENDING")

    def test_should_return_in_review_access_when_current_revision_is_pending(self):

        self.document.revisions.all().delete()
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.PENDING,
            author=self.responsible,
        )

        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "IN_REVIEW")

    def test_should_include_consolidated_metadata_in_the_response(self):
        detail = get_document_detail(self.document.id, user_id=self.responsible.id)

        self.assertEqual(detail["code"], "DOC-100")
        self.assertEqual(detail["project"]["code"], "PRJ")
        self.assertEqual(detail["discipline"]["code"], "CIV")
        self.assertEqual(detail["type"]["code"], "PDF")
        self.assertEqual(detail["responsible"]["email"], "responsible@example.com")
        self.assertEqual(detail["revision"]["version"], 1)
        self.assertEqual(detail["revision"]["status"], "APPROVED")
        self.assertEqual([a["acronym"] for a in detail["areas"]], ["ENG"])


class DocumentAccessRequestServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible2@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.requester = User.objects.create_user(
            email="requester@example.com",
            password="test-password",
            name="Requester",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-200",
            title="Documento restrito",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )

    def test_should_raise_document_not_found_for_missing_document(self):
        with self.assertRaises(DocumentNotFoundError):
            request_document_access(999999, self.requester.id)

    def test_should_raise_missing_user_when_no_user_id_is_given(self):
        with self.assertRaises(MissingUserError):
            request_document_access(self.document.id, None)

    def test_should_raise_user_not_found_for_unknown_user_id(self):
        with self.assertRaises(UserNotFoundError):
            request_document_access(self.document.id, 999999)

    def test_should_create_a_pending_access_request(self):
        result = request_document_access(
            self.document.id, self.requester.id, justification="Preciso revisar o projeto"
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["status"], "PENDING")
        access = DocumentAccess.objects.get(document=self.document, user=self.requester)
        self.assertEqual(access.justification, "Preciso revisar o projeto")
        self.assertIsNotNone(access.requested_at)

    def test_should_not_duplicate_an_existing_access_request(self):
        DocumentAccess.objects.create(
            document=self.document,
            user=self.requester,
            status=AccessStatus.PENDING,
            requested_at=timezone.now(),
        )

        result = request_document_access(self.document.id, self.requester.id)

        self.assertFalse(result["created"])
        self.assertEqual(
            DocumentAccess.objects.filter(document=self.document, user=self.requester).count(), 1
        )


class DocumentDetailViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible3@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-300",
            title="Documento view",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.responsible,
            auditor=self.responsible,
            audited_at=timezone.now(),
        )
        self.client = Client()

    def test_should_return_200_with_document_metadata(self):
        response = self.client.get(f"/documents/{self.document.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], "DOC-300")

    def test_should_return_404_for_missing_document(self):
        response = self.client.get("/documents/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_return_404_for_non_numeric_id(self):
        response = self.client.get("/documents/not-a-number")

        self.assertEqual(response.status_code, 404)


class RequestAccessViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible4@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.requester = User.objects.create_user(
            email="requester2@example.com",
            password="test-password",
            name="Requester",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-400",
            title="Documento acesso",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        self.client = Client()

    def test_should_return_201_when_access_request_is_created(self):
        response = self.client.post(
            f"/documents/{self.document.id}/request-access",
            data={"user_id": self.requester.id, "justification": "Preciso acessar"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING")

    def test_should_return_404_for_missing_document(self):
        response = self.client.post(
            "/documents/999999/request-access",
            data={"user_id": self.requester.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_should_return_400_when_user_id_is_missing(self):
        response = self.client.post(
            f"/documents/{self.document.id}/request-access",
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
