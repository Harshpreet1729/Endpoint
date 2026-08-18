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


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING="PENDING",'Pending'
        SUCCESS="SUCCESS","Success"
        FAILED="FAILED","Failed"

    def __str__(self):
        return f"{self.event} -> {self.endpoint}"

    event=models.ForeignKey(Event,on_delete=models.CASCADE)
    endpoint=models.ForeignKey(Endpoint,on_delete=models.CASCADE)
    status=models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    response_status_code=models.IntegerField(null=True, blank=True)
    response_body=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    attempt_count=models.IntegerField(default=1)
