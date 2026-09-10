"""Project system checks, reported by `manage.py check`."""

from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from core.models.choices import FileExtension
from core.models.upload_file_type import ALLOWED_FILE_TYPES


@register()
def upload_extensions_are_storable(app_configs, **kwargs):
    """Every extension the upload endpoint accepts must fit in `file`.

    The CHECK constraint on `file.extension` is generated from FileExtension,
    so a file accepted by the endpoint but missing from that enum is rejected
    the moment it is turned into a row — after the upload already succeeded.
    A warning rather than an error: the two lists are allowed to differ while
    the endpoint only sniffs part of the catalogue, and the application still
    has to boot.
    """
    orphans = sorted(
        file_type.extension
        for file_type in ALLOWED_FILE_TYPES
        if file_type.extension not in FileExtension.values
    )
    if not orphans:
        return []
    return [
        CheckWarning(
            "Upload accepts extensions the file table cannot store: "
            f"{orphans}.",
            hint=(
                "Add them to core.models.choices.FileExtension and run "
                "makemigrations (ck_file_extension is built from it), or drop "
                "them from ALLOWED_FILE_TYPES in "
                "core/models/upload_file_type.py. Storable now: "
                f"{sorted(FileExtension.values)}."
            ),
            id="core.W001",
        )
    ]
