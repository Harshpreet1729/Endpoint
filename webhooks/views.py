from rest_framework import generics
from .models import Endpoint, Event
from .serializers import EndpointSerializers, EventSerializers
from rest_framework.permissions import IsAuthenticated
from .tasks import deliver_event_task

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