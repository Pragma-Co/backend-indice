"""Relational models (PostgreSQL) for the document library.

Split by subject so each module stays readable; the app label remains `core`.
"""

from core.models.access import DocumentAccess
from core.models.audit import AuditLog
from core.models.catalog import (
    Discipline,
    DocumentType,
    Project,
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
from core.models.excluded_identifier import ExcludedIdentifier
from core.models.legal import (
    LegalClause,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentVersion,
    UserClauseConsent,
    UserLegalAcceptance,
)
from core.models.organization import Area, User
from core.models.revision import MAX_FILE_SIZE_BYTES, File, Revision
from core.models.search import DocumentContent

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
    "DocumentContent",
    "DocumentTag",
    "DocumentType",
    "ExcludedIdentifier",
    "File",
    "FileExtension",
    "LegalClause",
    "LegalDocument",
    "LegalDocumentStatus",
    "LegalDocumentVersion",
    "Project",
    "Revision",
    "RevisionStatus",
    "Role",
    "Tag",
    "User",
    "UserClauseConsent",
    "UserLegalAcceptance",
]
