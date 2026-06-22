from django.db import models


class FHIRResourceVersion(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    resource_type = models.CharField(max_length=64)
    logical_id = models.CharField(max_length=128)
    version_id = models.PositiveIntegerField()
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    source_app = models.CharField(max_length=100)
    source_model = models.CharField(max_length=100)
    source_pk = models.CharField(max_length=255)
    resource = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['resource_type', 'logical_id', '-version_id']
        unique_together = ('resource_type', 'logical_id', 'version_id')
        indexes = [
            models.Index(fields=['resource_type', 'logical_id']),
            models.Index(fields=['source_app', 'source_model', 'source_pk']),
            models.Index(fields=['recorded_at']),
        ]

    def __str__(self):
        return f"{self.resource_type}/{self.logical_id}/_history/{self.version_id}"
