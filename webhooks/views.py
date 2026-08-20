from rest_framework import generics
from .models import Endpoint
from .serializers import EndpointSerializers
from rest_framework.permissions import IsAuthenticated

class EndpointListClassView(generics.ListCreateAPIView):
    serializer_class=EndpointSerializers
    permission_classes=[IsAuthenticated]

    def get_queryset(self):
        return Endpoint.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
