from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentContent,
    DocumentType,
    Project,
    Role,
    Tag,
    User,
)
from core.services.document_exceptions import DocumentQueryError
from core.services.document_recommendation_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    get_document_recommendations,
)
from core.services.documents_exceptions import DocumentNotFoundError


def collection(payload, key):
    return next(item for item in payload["collections"] if item["key"] == key)


def codes(payload, key):
    return [item["code"] for item in collection(payload, key)["items"]]


class DocumentRecommendationFixtureMixin:
    def setUp(self):
        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manufacturing = Area.objects.create(acronym="MFG", name="Manufatura e Montagem")
        self.author = User.objects.create_user(
            email="author@example.com",
            password="secret",
            name="Author",
            role=Role.AUTHOR,
            area=self.structures,
        )
        self.fuselage = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.wing = Project.objects.create(code="AK-3100", name="Asa")
        self.structural = Discipline.objects.create(code="EST", name="Estruturas")
        self.hydraulics = Discipline.objects.create(code="HID", name="Sistemas Hidráulicos")
        self.drawing = DocumentType.objects.create(code="DWG", name="Desenho")
        self.memo = DocumentType.objects.create(code="MEM", name="Memorial de Cálculo")
        self.fatigue = Tag.objects.create(name="fadiga")
        self.titanium = Tag.objects.create(name="titânio")
        self.document = self._document(
            "AK-2100-EST-DWG-0001",
            tags=[self.fatigue, self.titanium],
            themes=["carga", "ensaio"],
        )
        self.client = Client()

    def _document(
        self,
        code,
        project=None,
        discipline=None,
        document_type=None,
        area=None,
        tags=(),
        themes=None,
    ):
        document = Document.objects.create(
            code=code,
            title=f"Documento {code}",
            project=project or self.fuselage,
            discipline=discipline or self.structural,
            document_type=document_type or self.drawing,
            confidentiality_level="PUBLIC",
            responsible=self.author,
            created_by=self.author,
        )
        document.areas.add(area or self.structures)
        for tag in tags:
            document.tags.add(tag)
        if themes is not None:
            DocumentContent.objects.create(
                document=document, content=" ".join(themes), thematic_tags=themes
            )
        return document

    def _unrelated(self, code):
        return self._document(
            code,
            project=self.wing,
            discipline=self.hydraulics,
            document_type=self.memo,
            area=self.manufacturing,
        )


class DocumentRecommendationServiceTests(DocumentRecommendationFixtureMixin, TestCase):
    def test_should_rank_related_documents_by_affinity_score(self):
        self._document(
            "AK-2100-HID-MEM-0001",
            discipline=self.hydraulics,
            document_type=self.memo,
            area=self.manufacturing,
            tags=[self.fatigue],
        )
        self._document(
            "AK-3100-HID-MEM-0001",
            project=self.wing,
            discipline=self.hydraulics,
            document_type=self.memo,
            area=self.manufacturing,
            tags=[self.fatigue, self.titanium],
        )
        self._document(
            "AK-3100-HID-MEM-0002",
            project=self.wing,
            discipline=self.hydraulics,
            document_type=self.memo,
            area=self.manufacturing,
            tags=[self.titanium],
        )

        payload = get_document_recommendations(self.document.id, {})

        self.assertEqual(
            codes(payload, "theme"),
            ["AK-2100-HID-MEM-0001", "AK-3100-HID-MEM-0001", "AK-3100-HID-MEM-0002"],
        )
        self.assertEqual(
            [item["score"] for item in collection(payload, "theme")["items"]], [5.0, 4.0, 2.0]
        )

    def test_should_report_the_shared_tags_and_metadata_of_each_match(self):
        self._document(
            "AK-3100-EST-DWG-0001",
            project=self.wing,
            area=self.manufacturing,
            tags=[self.titanium, self.fatigue],
        )

        payload = get_document_recommendations(self.document.id, {})

        item = collection(payload, "theme")["items"][0]
        self.assertEqual(item["score"], 7.0)
        self.assertEqual(
            item["matches"],
            {
                "project": False,
                "discipline": True,
                "type": True,
                "tags": ["fadiga", "titânio"],
                "areas": [],
                "themes": [],
            },
        )

    def test_should_match_thematic_tags_of_the_indexed_content(self):
        self._document(
            "AK-3100-HID-MEM-0001",
            project=self.wing,
            discipline=self.hydraulics,
            document_type=self.memo,
            area=self.manufacturing,
            themes=["ponte", "carga"],
        )

        payload = get_document_recommendations(self.document.id, {})

        self.assertEqual(codes(payload, "theme"), ["AK-3100-HID-MEM-0001"])
        self.assertEqual(collection(payload, "theme")["items"][0]["matches"]["themes"], ["carga"])
        self.assertEqual(collection(payload, "theme")["items"][0]["score"], 1.0)

    def test_should_group_matches_by_project_discipline_and_area(self):
        self._document("AK-2100-HID-MEM-0001", discipline=self.hydraulics, area=self.manufacturing)
        self._document("AK-3100-EST-MEM-0001", project=self.wing, area=self.manufacturing)
        self._document(
            "AK-3100-HID-MEM-0001",
            project=self.wing,
            discipline=self.hydraulics,
            document_type=self.memo,
        )

        payload = get_document_recommendations(self.document.id, {})

        self.assertEqual(codes(payload, "project"), ["AK-2100-HID-MEM-0001"])
        self.assertEqual(codes(payload, "discipline"), ["AK-3100-EST-MEM-0001"])
        self.assertEqual(codes(payload, "area"), ["AK-3100-HID-MEM-0001"])
        self.assertEqual(codes(payload, "theme"), [])

    def test_should_leave_the_theme_collection_empty_for_a_document_without_tags_or_content(self):
        bare = self._document("AK-2100-EST-DWG-0002")
        self._document("AK-2100-HID-MEM-0001", discipline=self.hydraulics, area=self.manufacturing)

        payload = get_document_recommendations(bare.id, {})

        self.assertEqual(collection(payload, "theme")["count"], 0)
        self.assertEqual(
            codes(payload, "project"), ["AK-2100-EST-DWG-0001", "AK-2100-HID-MEM-0001"]
        )

    def test_should_return_empty_collections_when_nothing_is_related(self):
        alone = self._unrelated("AK-3100-HID-MEM-0001")

        payload = get_document_recommendations(alone.id, {})

        self.assertEqual(
            [(item["key"], item["count"], item["items"]) for item in payload["collections"]],
            [("theme", 0, []), ("project", 0, []), ("discipline", 0, []), ("area", 0, [])],
        )

    def test_should_ignore_itself_archived_documents_and_inactive_types(self):
        archived = self._document("AK-2100-EST-DWG-0002")
        Document.objects.filter(pk=archived.pk).update(
            archived_at=timezone.now(), archived_by=self.author
        )
        inactive_type = DocumentType.objects.create(code="OLD", name="Antigo", active=False)
        self._document("AK-2100-EST-OLD-0001", document_type=inactive_type)
        self._document("AK-2100-EST-MEM-0001", document_type=self.memo)

        payload = get_document_recommendations(self.document.id, {})

        self.assertEqual(codes(payload, "project"), ["AK-2100-EST-MEM-0001"])

    def test_should_break_ties_in_favour_of_the_most_recent_document(self):
        self._document("AK-2100-EST-MEM-0001", document_type=self.memo)
        self._document("AK-2100-EST-MEM-0002", document_type=self.memo)

        payload = get_document_recommendations(self.document.id, {})

        self.assertEqual(
            codes(payload, "project"), ["AK-2100-EST-MEM-0002", "AK-2100-EST-MEM-0001"]
        )

    def test_should_limit_the_items_of_each_collection_and_keep_the_total_count(self):
        for number in range(1, 4):
            self._document(f"AK-2100-EST-MEM-000{number}", document_type=self.memo)

        payload = get_document_recommendations(self.document.id, {"limit": "1"})

        self.assertEqual(payload["limit"], 1)
        self.assertEqual(collection(payload, "project")["count"], 3)
        self.assertEqual(codes(payload, "project"), ["AK-2100-EST-MEM-0003"])

    def test_should_use_the_default_limit_and_cap_the_maximum(self):
        default_payload = get_document_recommendations(self.document.id, {})
        capped_payload = get_document_recommendations(self.document.id, {"limit": "500"})

        self.assertEqual(default_payload["limit"], DEFAULT_LIMIT)
        self.assertEqual(capped_payload["limit"], MAX_LIMIT)

    def test_should_reject_an_invalid_limit(self):
        with self.assertRaises(DocumentQueryError) as raised:
            get_document_recommendations(self.document.id, {"limit": "0"})

        self.assertEqual(raised.exception.errors["limit"]["code"], "invalid")

    def test_should_raise_for_an_unknown_or_archived_document(self):
        archived = self._document("AK-2100-EST-DWG-0002")
        Document.objects.filter(pk=archived.pk).update(
            archived_at=timezone.now(), archived_by=self.author
        )

        with self.assertRaises(DocumentNotFoundError):
            get_document_recommendations(archived.id, {})
        with self.assertRaises(DocumentNotFoundError):
            get_document_recommendations(999999, {})


class DocumentRecommendationViewTests(DocumentRecommendationFixtureMixin, TestCase):
    def url(self, document_id):
        return reverse("document-recommendations", args=[document_id])

    def test_should_answer_the_collections_with_the_listing_fields_of_each_item(self):
        self._document("AK-2100-EST-MEM-0001", document_type=self.memo, tags=[self.fatigue])

        response = self.client.get(self.url(self.document.id))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["document"],
            {"id": self.document.id, "code": self.document.code, "title": self.document.title},
        )
        self.assertEqual(
            [item["key"] for item in payload["collections"]],
            ["theme", "project", "discipline", "area"],
        )
        item = collection(payload, "theme")["items"][0]
        self.assertEqual(
            sorted(item),
            sorted(
                [
                    "id",
                    "code",
                    "title",
                    "description",
                    "type",
                    "discipline",
                    "areas",
                    "revision",
                    "status",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "score",
                    "matches",
                ]
            ),
        )
        self.assertEqual(item["areas"], [{"acronym": "EST", "name": "Engenharia Estrutural"}])
        self.assertEqual(item["score"], 8.0)

    def test_should_pass_the_limit_from_the_query_string(self):
        self._document("AK-2100-EST-MEM-0001", document_type=self.memo)
        self._document("AK-2100-EST-MEM-0002", document_type=self.memo)

        response = self.client.get(self.url(self.document.id), {"limit": 1})

        self.assertEqual(response.json()["limit"], 1)
        self.assertEqual(len(collection(response.json(), "project")["items"]), 1)

    def test_should_answer_400_for_an_invalid_limit(self):
        response = self.client.get(self.url(self.document.id), {"limit": "abc"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["limit"]["code"], "invalid")

    def test_should_answer_404_for_an_unknown_document(self):
        response = self.client.get(self.url(999999))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_reject_methods_other_than_get(self):
        response = self.client.post(self.url(self.document.id))

        self.assertEqual(response.status_code, 405)
