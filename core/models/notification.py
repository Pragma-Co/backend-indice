from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models.choices import NotificationType
from core.models.document import Document


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=False,
    )
    type = models.CharField(max_length=20, choices=NotificationType.choices)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=400)
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=NotificationType.values),
                name="ck_notification_type",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "-created_at", "-id"], name="ix_notification_recent"),
            models.Index(
                fields=["recipient"],
                condition=models.Q(read_at__isnull=True),
                name="ix_notification_unread",
            ),
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.type} @{self.document_id}"

    @property
    def is_new(self):
        return self.read_at is None
