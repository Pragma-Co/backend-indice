from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.catalog import Project
from core.models.choices import AccessGroupScope, ConfidentialityLevel, VisibilityScope
from core.models.organization import Area


class SecrecyLevel(models.Model):
    code = models.CharField(max_length=12, primary_key=True, choices=ConfidentialityLevel.choices)
    name = models.CharField(max_length=60, unique=True)
    rank = models.PositiveSmallIntegerField(unique=True)
    visibility = models.CharField(max_length=20, choices=VisibilityScope.choices)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "secrecy_level"
        ordering = ["rank"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__in=ConfidentialityLevel.values),
                name="ck_secrecy_level_code",
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=VisibilityScope.values),
                name="ck_secrecy_level_visibility",
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class AccessGroup(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=500, blank=True)
    scope = models.CharField(max_length=10, choices=AccessGroupScope.choices)
    area = models.ForeignKey(
        Area, null=True, blank=True, on_delete=models.PROTECT, related_name="access_groups"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="access_groups"
    )
    secrecy_level = models.ForeignKey(
        SecrecyLevel, on_delete=models.PROTECT, related_name="access_groups"
    )
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_access_groups",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="core.AccessGroupMember",
        through_fields=("group", "user"),
        related_name="access_groups",
    )

    class Meta:
        db_table = "access_group"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="ck_access_group_name_not_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(scope__in=AccessGroupScope.values),
                name="ck_access_group_scope",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(scope=AccessGroupScope.AREA, area__isnull=False, project__isnull=True)
                    | models.Q(
                        scope=AccessGroupScope.PROJECT, project__isnull=False, area__isnull=True
                    )
                ),
                name="ck_access_group_target",
            ),
            models.UniqueConstraint(
                fields=["area", "secrecy_level"],
                condition=models.Q(area__isnull=False),
                name="uq_access_group_area_level",
            ),
            models.UniqueConstraint(
                fields=["project", "secrecy_level"],
                condition=models.Q(project__isnull=False),
                name="uq_access_group_project_level",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.secrecy_level_id})"


class AccessGroupMember(models.Model):
    group = models.ForeignKey(
        AccessGroup, on_delete=models.CASCADE, related_name="memberships", db_index=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_group_memberships",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="added_access_group_members",
    )
    added_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "access_group_member"
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="uq_access_group_member"),
        ]

    def __str__(self):
        return f"{self.user_id}@{self.group_id}"
