import uuid
from django.db import models
from django.conf import settings
class ExportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scope = models.CharField(max_length=10)
    target = models.CharField(max_length=200, blank=True)
    ocr = models.BooleanField(default=False)
    vision = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default='queued')
    message = models.TextField(blank=True)
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
