from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.choices import BackupStatus, BackupTarget


class BackupRun(models.Model):
    target = models.CharField(max_length=10, choices=BackupTarget.choices)
    status = models.CharField(
        max_length=10, choices=BackupStatus.choices, default=BackupStatus.RUNNING
    )
    started_at = models.DateTimeField(db_default=Now(), editable=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    destination = models.CharField(max_length=500, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    encrypted = models.BooleanField(default=False)
    record_count = models.IntegerField(null=True, blank=True)
    error = models.CharField(max_length=120, blank=True)
    pruned_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="triggered_backups",
    )

    class Meta:
        db_table = "backup_run"
        ordering = ["-started_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target__in=BackupTarget.values), name="ck_backup_run_target"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=BackupStatus.values), name="ck_backup_run_status"
            ),
        ]
        indexes = [
            models.Index(fields=["target", "-started_at"], name="ix_backup_run_target"),
        ]

    def __str__(self):
        return f"{self.target} {self.status} {self.started_at:%Y-%m-%d %H:%M}"
