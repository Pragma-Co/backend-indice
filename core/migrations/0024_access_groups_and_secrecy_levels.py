import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models

SECRECY_LEVELS = (
    ("PUBLIC", "Público", 0, "EVERYONE", "Visível para todos os usuários."),
    ("CONFIDENTIAL", "Sigiloso", 1, "AREA", "Visível para os usuários das áreas do documento."),
    ("SECRET", "Restrito", 2, "SELECTED_USERS", "Visível apenas para usuários selecionados."),
)

ADD_DOCUMENT_LEVEL_FK = """
    ALTER TABLE document
        ADD CONSTRAINT fk_document_confidentiality_level
        FOREIGN KEY (confidentiality_level) REFERENCES secrecy_level (code)
        ON DELETE RESTRICT;
"""

DROP_DOCUMENT_LEVEL_FK = (
    "ALTER TABLE document DROP CONSTRAINT IF EXISTS fk_document_confidentiality_level;"
)


def seed_secrecy_levels(apps, schema_editor):
    SecrecyLevel = apps.get_model("core", "SecrecyLevel")
    for code, name, rank, visibility, description in SECRECY_LEVELS:
        SecrecyLevel.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "rank": rank,
                "visibility": visibility,
                "description": description,
            },
        )


def remove_secrecy_levels(apps, schema_editor):
    SecrecyLevel = apps.get_model("core", "SecrecyLevel")
    SecrecyLevel.objects.filter(code__in=[level[0] for level in SECRECY_LEVELS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0023_document_access_type_and_expiry")]

    operations = [
        migrations.CreateModel(
            name="SecrecyLevel",
            fields=[
                (
                    "code",
                    models.CharField(
                        choices=[
                            ("PUBLIC", "Public"),
                            ("CONFIDENTIAL", "Confidential"),
                            ("SECRET", "Secret"),
                        ],
                        max_length=12,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=60, unique=True)),
                ("rank", models.PositiveSmallIntegerField(unique=True)),
                (
                    "visibility",
                    models.CharField(
                        choices=[
                            ("EVERYONE", "Everyone"),
                            ("AREA", "Users of the document areas"),
                            ("SELECTED_USERS", "Selected users"),
                        ],
                        max_length=20,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "db_table": "secrecy_level",
                "ordering": ["rank"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__in", ["PUBLIC", "CONFIDENTIAL", "SECRET"])),
                        name="ck_secrecy_level_code",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("visibility__in", ["EVERYONE", "AREA", "SELECTED_USERS"])
                        ),
                        name="ck_secrecy_level_visibility",
                    ),
                ],
            },
        ),
        migrations.RunPython(seed_secrecy_levels, remove_secrecy_levels),
        migrations.RunSQL(ADD_DOCUMENT_LEVEL_FK, DROP_DOCUMENT_LEVEL_FK),
        migrations.CreateModel(
            name="AccessGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.CharField(blank=True, max_length=500)),
                (
                    "scope",
                    models.CharField(
                        choices=[("AREA", "Area"), ("PROJECT", "Project")], max_length=10
                    ),
                ),
                ("active", models.BooleanField(default=True)),
                (
                    "created_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "area",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="access_groups",
                        to="core.area",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="access_groups",
                        to="core.project",
                    ),
                ),
                (
                    "secrecy_level",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="access_groups",
                        to="core.secrecylevel",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_access_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "access_group",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="AccessGroupMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "added_at",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="core.accessgroup",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_group_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "added_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="added_access_group_members",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "access_group_member"},
        ),
        migrations.AddField(
            model_name="accessgroup",
            name="members",
            field=models.ManyToManyField(
                related_name="access_groups",
                through="core.AccessGroupMember",
                through_fields=("group", "user"),
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroupmember",
            constraint=models.UniqueConstraint(
                fields=("group", "user"), name="uq_access_group_member"
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroup",
            constraint=models.CheckConstraint(
                condition=models.Q(("name__regex", "\\S")), name="ck_access_group_name_not_blank"
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroup",
            constraint=models.CheckConstraint(
                condition=models.Q(("scope__in", ["AREA", "PROJECT"])), name="ck_access_group_scope"
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroup",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("area__isnull", False), ("project__isnull", True), ("scope", "AREA")),
                    models.Q(
                        ("area__isnull", True), ("project__isnull", False), ("scope", "PROJECT")
                    ),
                    _connector="OR",
                ),
                name="ck_access_group_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("area__isnull", False)),
                fields=("area", "secrecy_level"),
                name="uq_access_group_area_level",
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("project__isnull", False)),
                fields=("project", "secrecy_level"),
                name="uq_access_group_project_level",
            ),
        ),
    ]
