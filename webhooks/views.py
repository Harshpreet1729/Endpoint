from rest_framework import generics
from .models import Endpoint, Event
from .serializers import EndpointSerializers, EventSerializers
from rest_framework.permissions import IsAuthenticated

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
        serializer.save(owner=self.request.user)
