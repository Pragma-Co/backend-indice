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


class FileExtension(models.TextChoices):
    PDF = "pdf", "PDF"
    DWG = "dwg", "AutoCAD drawing"
    DXF = "dxf", "Drawing exchange format"
    DOC = "doc", "Word document (legacy)"
    DOCX = "docx", "Word document"
    XLS = "xls", "Excel spreadsheet (legacy)"
    XLSX = "xlsx", "Excel spreadsheet"
