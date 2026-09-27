"""Django admin registration.

The product UI is the Vue frontend; this is the maintenance back door for the
catalog tables and for inspecting the audit trail.

`project_discipline`, `document_area` and `document_tag` use composite primary
keys, which the admin does not support, so those links cannot be edited here —
use the API or the shell (`DocumentArea.objects.create(...)`).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from core.models import (
    Area,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    File,
    Project,
    Revision,
    Tag,
    User,
)


class CoreUserCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email", "name", "role", "area")


class CoreUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = CoreUserChangeForm
    add_form = CoreUserCreationForm
    list_display = ("email", "name", "role", "area", "is_active")
    list_filter = ("role", "is_active", "area")
    search_fields = ("email", "name")
    ordering = ("name",)
    # No groups/permissions on this model: admin access comes from `role`
    filter_horizontal = ()
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "role", "area")}),
        ("Status", {"fields": ("is_active", "terms_accepted_at", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "role", "area", "password1", "password2"),
            },
        ),
    )


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "manager", "active")
    list_filter = ("active",)
    search_fields = ("acronym", "name")
    autocomplete_fields = ("manager",)
    readonly_fields = ("created_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    list_filter = ("active",)
    search_fields = ("code", "name")
    readonly_fields = ("created_at",)
    # ManyToMany through an explicit model is not editable in a form
    exclude = ("disciplines",)


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    list_filter = ("active",)
    search_fields = ("code", "name")


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")
    list_filter = ("active",)
    search_fields = ("code", "name")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "title",
        "project",
        "discipline",
        "document_type",
        "confidentiality_level",
        "responsible",
    )
    list_filter = (
        "confidentiality_level",
        "project",
        "discipline",
        "document_type",
    )
    search_fields = ("code", "title", "description")
    autocomplete_fields = ("project", "discipline", "document_type", "responsible")
    readonly_fields = ("created_at", "updated_at")
    exclude = ("areas", "tags")


class FileInline(admin.TabularInline):
    model = File
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ("document", "version", "status", "issue_date", "author", "auditor")
    list_filter = ("status",)
    search_fields = ("document__code", "document__title")
    autocomplete_fields = ("document", "author", "auditor")
    readonly_fields = ("created_at",)
    inlines = [FileInline]


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "revision", "extension", "size_bytes", "sha256")
    list_filter = ("extension",)
    search_fields = ("original_name", "sha256", "storage_path")
    autocomplete_fields = ("revision",)
    readonly_fields = ("uploaded_at",)


@admin.register(DocumentAccess)
class DocumentAccessAdmin(admin.ModelAdmin):
    list_display = ("document", "user", "status", "requested_at", "approver", "decided_at")
    list_filter = ("status",)
    search_fields = ("document__code", "user__email")
    autocomplete_fields = ("document", "user", "approver")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: the table is append-only at the database level."""

    list_display = ("occurred_at", "user", "action", "entity", "entity_id", "ip_address")
    list_filter = ("action", "entity")
    search_fields = ("entity", "entity_id", "user__email")
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
