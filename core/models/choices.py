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


class AccessType(models.TextChoices):
    TEMPORARY = "TEMPORARY", "Temporary"
    PERMANENT = "PERMANENT", "Permanent"


class NotificationType(models.TextChoices):
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED", "Document updated"
    ACCESS_APPROVED = "ACCESS_APPROVED", "Access approved"
    ACCESS_REJECTED = "ACCESS_REJECTED", "Access rejected"


class VisibilityScope(models.TextChoices):
    EVERYONE = "EVERYONE", "Everyone"
    AREA = "AREA", "Users of the document areas"
    SELECTED_USERS = "SELECTED_USERS", "Selected users"


class AccessGroupScope(models.TextChoices):
    AREA = "AREA", "Area"
    PROJECT = "PROJECT", "Project"


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
    DOC_CAPTURE_ATTEMPT = "DOC_CAPTURE_ATTEMPT", "Document capture attempt"


class FileExtension(models.TextChoices):
    PDF = "pdf", "PDF"
    DOC = "doc", "Word document (legacy)"
    DOCX = "docx", "Word document"
    JPEG = "jpeg", "JPEG image"
    PNG = "png", "PNG image"


class IncidentType(models.TextChoices):
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS", "Unauthorized access"
    IMPROPER_DISCLOSURE = "IMPROPER_DISCLOSURE", "Improper disclosure"
    DATA_LOSS = "DATA_LOSS", "Loss or destruction of data"
    CREDENTIAL_EXPOSURE = "CREDENTIAL_EXPOSURE", "Credential exposure"
    MISDIRECTED_DELIVERY = "MISDIRECTED_DELIVERY", "Data sent to the wrong recipient"
    MALICIOUS_SOFTWARE = "MALICIOUS_SOFTWARE", "Malicious software"
    OTHER = "OTHER", "Other"


class IncidentSeverity(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class IncidentStatus(models.TextChoices):
    REPORTED = "REPORTED", "Reported"
    CONTAINMENT = "CONTAINMENT", "Under containment"
    ANALYSIS = "ANALYSIS", "Under analysis"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class PersonalDataCategory(models.TextChoices):
    IDENTIFICATION = "IDENTIFICATION", "Identification (name, email)"
    CREDENTIALS = "CREDENTIALS", "Credentials"
    PROFESSIONAL = "PROFESSIONAL", "Professional data (role, area)"
    ACCESS_HISTORY = "ACCESS_HISTORY", "Access and audit history"
    DOCUMENT_CONTENT = "DOCUMENT_CONTENT", "Content of technical documents"
    OTHER = "OTHER", "Other"


class IncidentActionKind(models.TextChoices):
    CONTAINMENT = "CONTAINMENT", "Containment"
    ERADICATION = "ERADICATION", "Eradication"
    RECOVERY = "RECOVERY", "Recovery"
    COMMUNICATION = "COMMUNICATION", "Communication"
    OTHER = "OTHER", "Other"


class NotificationRecipient(models.TextChoices):
    AUTHORITY = "AUTHORITY", "Data protection authority"
    DATA_SUBJECTS = "DATA_SUBJECTS", "Data subjects"


class BackupTarget(models.TextChoices):
    POSTGRES = "POSTGRES", "PostgreSQL"
    MONGODB = "MONGODB", "MongoDB"


class BackupStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
