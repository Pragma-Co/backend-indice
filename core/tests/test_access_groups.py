from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

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
    SecrecyLevel,
    User,
    VisibilityScope,
)
from core.services.access_group_service import can_user_view_document


class AccessGroupFixtureMixin:
    def setUp(self):
        self.structures = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.manufacturing = Area.objects.create(acronym="MFG", name="Manufatura e Montagem")
        self.author = self._user("author@example.com", Role.AUTHOR, self.structures)
        self.colleague = self._user("colleague@example.com", Role.VIEWER, self.structures)
        self.outsider = self._user("outsider@example.com", Role.VIEWER, self.manufacturing)
        self.manager = self._user("manager@example.com", Role.AUDITOR, self.structures)
        self.fuselage = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.wing = Project.objects.create(code="AK-3100", name="Asa")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.public_document = self._document("AK-2100-EST-DWG-0001", ConfidentialityLevel.PUBLIC)
        self.confidential_document = self._document(
            "AK-2100-EST-DWG-0002", ConfidentialityLevel.CONFIDENTIAL
        )
        self.secret_document = self._document("AK-2100-EST-DWG-0003", ConfidentialityLevel.SECRET)
        self.levels = {level.code: level for level in SecrecyLevel.objects.all()}

    def _user(self, email, role, area, active=True):
        return User.objects.create_user(
            email=email,
            password="secret",
            name=email.split("@")[0],
            role=role,
            area=area,
            is_active=active,
        )

    def _document(self, code, level, project=None):
        document = Document.objects.create(
            code=code,
            title=f"Documento {code}",
            project=project or self.fuselage,
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

    def _grant(self, document, user, access_type=AccessType.PERMANENT, expires_on=None):
        return DocumentAccess.objects.create(
            document=document,
            user=user,
            status=AccessStatus.APPROVED,
            access_type=access_type,
            expires_on=expires_on,
            approver=self.manager,
            decided_at=timezone.now(),
        )


class SecrecyLevelModelTests(AccessGroupFixtureMixin, TestCase):
    def test_should_provide_the_three_levels_ordered_by_rank_from_the_migration(self):
        levels = list(SecrecyLevel.objects.values_list("code", "name", "rank", "visibility"))

        self.assertEqual(
            levels,
            [
                ("PUBLIC", "Público", 0, VisibilityScope.EVERYONE),
                ("CONFIDENTIAL", "Sigiloso", 1, VisibilityScope.AREA),
                ("SECRET", "Restrito", 2, VisibilityScope.SELECTED_USERS),
            ],
        )

    def test_should_reject_a_level_outside_the_confidentiality_enumeration(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SecrecyLevel.objects.create(
                code="TOP", name="Ultra", rank=3, visibility=VisibilityScope.SELECTED_USERS
            )

    def test_should_reject_an_unknown_visibility_rule(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SecrecyLevel.objects.filter(code="PUBLIC").update(visibility="FRIENDS")

    def test_should_keep_a_level_referenced_by_documents(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SecrecyLevel.objects.filter(code="PUBLIC").delete()

        self.assertTrue(SecrecyLevel.objects.filter(code="PUBLIC").exists())

    def test_should_reject_a_document_with_a_level_that_does_not_exist(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Document.objects.filter(pk=self.public_document.pk).update(confidentiality_level="TOP")


class AccessGroupModelTests(AccessGroupFixtureMixin, TestCase):
    def test_should_relate_a_group_to_its_area_level_creator_and_members(self):
        group = self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[self.outsider],
        )

        membership = group.memberships.get()
        self.assertEqual(group.area, self.structures)
        self.assertEqual(group.secrecy_level.code, "CONFIDENTIAL")
        self.assertEqual(group.created_by, self.manager)
        self.assertEqual(list(group.members.all()), [self.outsider])
        self.assertEqual(list(self.outsider.access_groups.all()), [group])
        self.assertEqual(membership.added_by, self.manager)
        self.assertIsNotNone(membership.added_at)

    def test_should_require_the_target_that_matches_the_scope(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroup.objects.create(
                name="Sem área",
                scope=AccessGroupScope.AREA,
                secrecy_level=self.levels["PUBLIC"],
                created_by=self.manager,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroup.objects.create(
                name="Projeto com área",
                scope=AccessGroupScope.PROJECT,
                area=self.structures,
                project=self.fuselage,
                secrecy_level=self.levels["PUBLIC"],
                created_by=self.manager,
            )

    def test_should_reject_a_scope_outside_the_enumeration_and_a_blank_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroup.objects.create(
                name="Escopo inválido",
                scope="TEAM",
                area=self.structures,
                secrecy_level=self.levels["PUBLIC"],
                created_by=self.manager,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroup.objects.create(
                name="   ",
                scope=AccessGroupScope.AREA,
                area=self.structures,
                secrecy_level=self.levels["PUBLIC"],
                created_by=self.manager,
            )

    def test_should_keep_one_group_per_target_and_level(self):
        self._group("Estruturas sigiloso", ConfidentialityLevel.CONFIDENTIAL, area=self.structures)
        self._group("Fuselagem restrito", ConfidentialityLevel.SECRET, project=self.fuselage)
        self._group("Estruturas restrito", ConfidentialityLevel.SECRET, area=self.structures)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._group(
                "Outro estruturas sigiloso", ConfidentialityLevel.CONFIDENTIAL, area=self.structures
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._group(
                "Outro fuselagem restrito", ConfidentialityLevel.SECRET, project=self.fuselage
            )

    def test_should_reject_the_same_user_twice_in_a_group(self):
        group = self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[self.outsider],
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroupMember.objects.create(group=group, user=self.outsider)

    def test_should_remove_memberships_with_the_group_and_with_the_user(self):
        group = self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[self.outsider, self.colleague],
        )
        other_group = self._group(
            "Fuselagem restrito",
            ConfidentialityLevel.SECRET,
            project=self.fuselage,
            members=[self.outsider],
        )

        group.delete()
        self.outsider.delete()

        self.assertEqual(AccessGroupMember.objects.count(), 0)
        self.assertTrue(AccessGroup.objects.filter(pk=other_group.pk).exists())

    def test_should_protect_the_area_project_level_and_creator_of_a_group(self):
        self._group("Estruturas sigiloso", ConfidentialityLevel.CONFIDENTIAL, area=self.structures)
        self._group("Fuselagem restrito", ConfidentialityLevel.SECRET, project=self.fuselage)

        with self.assertRaises(ProtectedError):
            self.structures.delete()
        with self.assertRaises(ProtectedError):
            self.fuselage.delete()
        with self.assertRaises(ProtectedError):
            self.levels["SECRET"].delete()
        with self.assertRaises(ProtectedError):
            self.manager.delete()


class ConfidentialityRuleTests(AccessGroupFixtureMixin, TestCase):
    def test_should_show_public_documents_to_every_active_user(self):
        inactive = self._user("inactive@example.com", Role.VIEWER, self.manufacturing, active=False)

        self.assertTrue(can_user_view_document(self.public_document, self.colleague))
        self.assertTrue(can_user_view_document(self.public_document, self.outsider))
        self.assertFalse(can_user_view_document(self.public_document, inactive))
        self.assertFalse(can_user_view_document(self.public_document, None))

    def test_should_show_confidential_documents_to_the_users_of_its_areas(self):
        self.assertTrue(can_user_view_document(self.confidential_document, self.colleague))
        self.assertFalse(can_user_view_document(self.confidential_document, self.outsider))

    def test_should_show_restricted_documents_only_to_selected_users(self):
        self._grant(self.secret_document, self.outsider)

        self.assertTrue(can_user_view_document(self.secret_document, self.author))
        self.assertTrue(can_user_view_document(self.secret_document, self.outsider))
        self.assertFalse(can_user_view_document(self.secret_document, self.colleague))

    def test_should_accept_an_approved_grant_on_confidential_documents_and_ignore_expired_ones(
        self,
    ):
        self._grant(self.confidential_document, self.outsider)
        expired = self._user("expired@example.com", Role.VIEWER, self.manufacturing)
        self._grant(
            self.secret_document,
            expired,
            access_type=AccessType.TEMPORARY,
            expires_on=timezone.localdate() - timedelta(days=1),
        )

        self.assertTrue(can_user_view_document(self.confidential_document, self.outsider))
        self.assertFalse(can_user_view_document(self.secret_document, expired))

    def test_should_grant_through_an_active_group_of_the_document_area_or_project(self):
        by_area = self._user("by.area@example.com", Role.VIEWER, self.manufacturing)
        by_project = self._user("by.project@example.com", Role.VIEWER, self.manufacturing)
        self._group(
            "Estruturas sigiloso",
            ConfidentialityLevel.CONFIDENTIAL,
            area=self.structures,
            members=[by_area],
        )
        self._group(
            "Fuselagem restrito",
            ConfidentialityLevel.SECRET,
            project=self.fuselage,
            members=[by_project],
        )

        self.assertTrue(can_user_view_document(self.confidential_document, by_area))
        self.assertFalse(can_user_view_document(self.secret_document, by_area))
        self.assertTrue(can_user_view_document(self.confidential_document, by_project))
        self.assertTrue(can_user_view_document(self.secret_document, by_project))

    def test_should_ignore_inactive_groups_and_groups_of_other_targets(self):
        inactive_member = self._user("inactive.group@example.com", Role.VIEWER, self.manufacturing)
        other_area_member = self._user("other.area@example.com", Role.VIEWER, self.manufacturing)
        other_project_member = self._user(
            "other.project@example.com", Role.VIEWER, self.manufacturing
        )
        self._group(
            "Estruturas restrito",
            ConfidentialityLevel.SECRET,
            area=self.structures,
            active=False,
            members=[inactive_member],
        )
        self._group(
            "Manufatura restrito",
            ConfidentialityLevel.SECRET,
            area=self.manufacturing,
            members=[other_area_member],
        )
        self._group(
            "Asa restrito",
            ConfidentialityLevel.SECRET,
            project=self.wing,
            members=[other_project_member],
        )

        self.assertFalse(can_user_view_document(self.confidential_document, inactive_member))
        self.assertFalse(can_user_view_document(self.confidential_document, other_area_member))
        self.assertFalse(can_user_view_document(self.secret_document, other_project_member))

    def test_should_not_let_a_lower_level_group_reach_a_higher_level_document(self):
        member = self._user("lower@example.com", Role.VIEWER, self.manufacturing)
        self._group(
            "Estruturas público",
            ConfidentialityLevel.PUBLIC,
            area=self.structures,
            members=[member],
        )

        self.assertFalse(can_user_view_document(self.confidential_document, member))
        self.assertFalse(can_user_view_document(self.secret_document, member))
