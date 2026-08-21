from django.db import models

from common.models import TimestampedModel


class BackupType(models.TextChoices):
    DATABASE = "DATABASE", "Database"
    PRIVATE_OBJECTS = "PRIVATE_OBJECTS", "Private objects"


class BackupStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class BackupRun(TimestampedModel):
    """Safe operational metadata only; backup contents and credentials never live here."""

    backup_type = models.CharField(max_length=24, choices=BackupType.choices)
    status = models.CharField(
        max_length=12, choices=BackupStatus.choices, default=BackupStatus.RUNNING
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")
    storage_reference = models.CharField(max_length=500, blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    duration_ms = models.PositiveBigIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["backup_type", "status", "-finished_at"],
                name="backup_type_status_idx",
            ),
        ]
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.backup_type} {self.started_at.isoformat()} ({self.status})"
