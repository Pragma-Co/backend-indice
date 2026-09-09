from django.contrib import admin

from core.models import Discipline, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("acronym", "name")
    ordering = ("name",)
