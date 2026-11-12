"""Relational models (PostgreSQL) for the document library.

Split by subject so each module stays readable; the app label remains `core`.
"""

from core.models.access import DocumentAccess, DocumentAccessGroup
from core.models.access_group import AccessGroup, AccessGroupMember, SecrecyLevel
from core.models.audit import AuditLog
from core.models.catalog import (
    Discipline,
    DocumentType,
    Project,
    Tag,
)
from core.models.choices import (
    AccessGroupScope,
    AccessStatus,
    AccessType,
    AuditAction,
    ConfidentialityLevel,
    FileExtension,
    NotificationType,
    RevisionStatus,
    Role,
    VisibilityScope,
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
from core.models.library import SavedDocument
from core.models.notification import Notification
from core.models.organization import Area, User
from core.models.revision import MAX_FILE_SIZE_BYTES, File, Revision
from core.models.search import DocumentContent
from core.models.search_history import SearchHistory

__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "AccessGroup",
    "AccessGroupMember",
    "AccessGroupScope",
    "AccessStatus",
    "AccessType",
    "Area",
    "AuditAction",
    "AuditLog",
    "ConfidentialityLevel",
    "Discipline",
    "Document",
    "DocumentAccess",
    "DocumentAccessGroup",
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
    "Notification",
    "NotificationType",
    "Project",
    "Revision",
    "RevisionStatus",
    "Role",
    "SavedDocument",
    "SearchHistory",
    "SecrecyLevel",
    "Tag",
    "User",
    "UserClauseConsent",
    "UserLegalAcceptance",
    "VisibilityScope",
]
