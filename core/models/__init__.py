"""Relational models (PostgreSQL) for the document library.

Split by subject so each module stays readable; the app label remains `core`.
"""

from core.models.access import DocumentAccess
from core.models.access_group import AccessGroup, AccessGroupMember, SecrecyLevel
from core.models.audit import AuditLog
from core.models.backup import BackupRun
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
    BackupStatus,
    BackupTarget,
    ConfidentialityLevel,
    FileExtension,
    IncidentActionKind,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    NotificationRecipient,
    PersonalDataCategory,
    RevisionStatus,
    Role,
    VisibilityScope,
)
from core.models.document import Document, DocumentArea, DocumentTag
from core.models.excluded_identifier import ExcludedIdentifier
from core.models.incident import (
    DataIncident,
    DataIncidentAction,
    DataIncidentAffectedDocument,
    DataIncidentAffectedUser,
    DataIncidentStatusChange,
)
from core.models.legal import (
    LegalClause,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentVersion,
    UserClauseConsent,
    UserLegalAcceptance,
)
from core.models.library import SavedDocument
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
    "BackupRun",
    "BackupStatus",
    "BackupTarget",
    "ConfidentialityLevel",
    "DataIncident",
    "DataIncidentAction",
    "DataIncidentAffectedDocument",
    "DataIncidentAffectedUser",
    "DataIncidentStatusChange",
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
    "IncidentActionKind",
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentType",
    "LegalClause",
    "LegalDocument",
    "LegalDocumentStatus",
    "LegalDocumentVersion",
    "NotificationRecipient",
    "PersonalDataCategory",
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
