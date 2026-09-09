"""Relational models (PostgreSQL) of the core app, one entity per module."""

from core.models.discipline import Discipline
from core.models.project import Project

__all__ = ["Discipline", "Project"]
