"""Relational models (PostgreSQL) for the document library.

Split by subject so each module stays readable; the app label remains `core`.
"""

from core.models.access import DocumentAccess
from core.models.audit import AuditLog
from core.models.catalog import (
    Discipline,
    DocumentType,
    Project,
    ProjectDiscipline,
    Tag,
)
from core.models.choices import (
    AccessStatus,
    AuditAction,
    ConfidentialityLevel,
    FileExtension,
    RevisionStatus,
    Role,
)
from core.models.document import Document, DocumentArea, DocumentTag
from core.models.organization import Area, User
from core.models.revision import MAX_FILE_SIZE_BYTES, File, Revision

__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "AccessStatus",
    "Area",
    "AuditAction",
    "AuditLog",
    "ConfidentialityLevel",
    "Discipline",
    "Document",
    "DocumentAccess",
    "DocumentArea",
    "DocumentTag",
    "DocumentType",
    "File",
    "FileExtension",
    "Project",
    "ProjectDiscipline",
    "Revision",
    "RevisionStatus",
    "Role",
    "Tag",
    "User",
]
