"""Enumerations shared by the relational models.

Every enum here is stored as VARCHAR and additionally guarded by a CHECK
constraint on the table (Django does not turn `choices` into a database
constraint on its own), so an invalid value cannot enter the database even
through raw SQL.
"""

from django.db import models


class Role(models.TextChoices):
    AUTHOR = "AUTHOR", "Author"
    VIEWER = "VIEWER", "Viewer"
    AUDITOR = "AUDITOR", "Auditor"
    ADMIN = "ADMIN", "Administrator"


class ConfidentialityLevel(models.TextChoices):
    PUBLIC = "PUBLIC", "Public"
    CONFIDENTIAL = "CONFIDENTIAL", "Confidential"
    SECRET = "SECRET", "Secret"


class RevisionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    OBSOLETE = "OBSOLETE", "Obsolete"


class AccessStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    READ = "READ", "Read"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    LOGIN = "LOGIN", "Login"
    DOC_UPLOAD_SUCCESS = "DOC_UPLOAD_SUCCESS", "Document upload succeeded"
    DOC_UPLOAD_DUPLICATE = "DOC_UPLOAD_DUPLICATE", "Duplicate document upload attempted"
    DOC_SUBMIT_SUCCESS = "DOC_SUBMIT_SUCCESS", "Document registration submitted"
    DOC_REVISION_CREATED = "DOC_REVISION_CREATED", "Document revision created"
    DOC_CANCEL = "DOC_CANCEL", "Document registration cancelled"
    DOC_DOWNLOAD = "DOC_DOWNLOAD", "Document downloaded"
    DOC_ACCESS_REQUESTED = "DOC_ACCESS_REQUESTED", "Document access requested"


class FileExtension(models.TextChoices):
    PDF = "pdf", "PDF"
    DOC = "doc", "Word document (legacy)"
    DOCX = "docx", "Word document"
    JPEG = "jpeg", "JPEG image"
    PNG = "png", "PNG image"
