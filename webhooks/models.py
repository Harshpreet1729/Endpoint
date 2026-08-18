from django.db import models
from django.conf import settings

# Create your models here.
class Endpoint(models.Model):
    name=models.CharField(max_length=100)
    url=models.URLField()
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE
    )

    def __str__(self):
        return self.name


class Event(models.Model):
    event_type=models.CharField(max_length=100)
    payload=models.JSONField()
    created_at=models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
        )

    def __str__(self):
        return self.event_type
