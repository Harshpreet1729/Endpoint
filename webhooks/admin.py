from django.contrib import admin
from .models import Endpoint, Event, Delivery, DeliveryAttempt
# Register your models here.
admin.site.register(Endpoint)
admin.site.register(Event)
admin.site.register(Delivery)
admin.site.register(DeliveryAttempt)
