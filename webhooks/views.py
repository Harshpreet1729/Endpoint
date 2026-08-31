from rest_framework import generics
from django.shortcuts import render
from .models import Endpoint, Event, Delivery, Subscriptions
from .serializers import EndpointSerializers, EventSerializers, SubscriptionsSerializers
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
        subscriptions=Subscriptions.objects.filter(
            endpoint__owner=self.request.user,
            endpoint__is_active=True,
            event_type=event.event_type
        )
        for subscription in subscriptions:
            deliver_event_task.delay(
                event.id,
                subscription.endpoint.id
        )

class SubscriptionClassView(generics.ListCreateAPIView):
    serializer_class=SubscriptionsSerializers
    permission_classes=[IsAuthenticated]

    def get_queryset(self):
        return Subscriptions.objects.filter(
            endpoint__owner=self.request.user
        )
    def perform_create(self, serializer):
        endpoint=serializer.validated_data["endpoint"]
        if endpoint.owner!=self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot subscribe other user's endpoint.")
        serializer.save()

@login_required
def dashboard(request):
    endpoints=Endpoint.objects.filter(owner=request.user)
    events=Event.objects.filter(owner=request.user)
    deliveries=Delivery.objects.filter(
        event__owner=request.user
    ).select_related(
        "event",
        "endpoint"
    ).order_by("-created_at")
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
        "recent_deliveries":deliveries[:10]
    }
    return render(
        request,
        "webhooks/dashboard.html",
        context
    )