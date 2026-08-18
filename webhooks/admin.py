from django.contrib import admin
from .models import Endpoint, Event
# Register your models here.
admin.site.register(Endpoint)
admin.site.register(Event)

