from rest_framework import generics
from django.shortcuts import render
from .models import Endpoint, Event, Delivery
from .serializers import EndpointSerializers, EventSerializers
from rest_framework.permissions import IsAuthenticated
from .tasks import deliver_event_task
from django.contrib.auth.decorators import login_required

class EndpointListClassView(generics.ListCreateAPIView):
    serializer_class=EndpointSerializers
    permission_classes=[IsAuthenticated]

    def get_queryset(self):
        return Endpoint.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class EventListClassView(generics.ListCreateAPIView):
    serializer_class=EventSerializers
    permission_classes=[IsAuthenticated]

    def get_queryset(self): 
        return Event.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        event = serializer.save(owner=self.request.user)
        endpoints=Endpoint.objects.filter(
            owner=self.request.user,
            is_active=True
        )
        for endpoint in endpoints:
            deliver_event_task.delay(event.id, endpoint.id)

@login_required
def dashboard(request):
    endpoints=Endpoint.objects.filter(owner=request.user)
    events=Event.objects.filter(owner=request.user)
    deliveries=Delivery.objects.filter(
        event__owner=request.user
    )
    context = {
        "endpoint_count": endpoints.count(),
        "event_count": events.count(),
        "success_count": deliveries.filter(
            status=Delivery.Status.SUCCESS
        ).count(),
        "failed_count": deliveries.filter(
            status=Delivery.Status.FAILED
        ).count(),
        "dead_letter_count": deliveries.filter(
            status=Delivery.Status.DEAD_LETTERED
        ).count(),
    }
    return render(
        request,
        "webhooks/dashboard.html",
        context
    )