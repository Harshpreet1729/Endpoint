from rest_framework import serializers
from .models import Endpoint, Event, Subscriptions

class EndpointSerializers(serializers.ModelSerializer):
    class Meta:
        model=Endpoint
        fields = [
            "id",
            "name",
            "url",
            "is_active",
            "created_at",
            "secret",
        ]

        read_only_fields = ["id", "created_at"]

        extra_kwargs = {
            "secret": {"write_only": True}
        }

class EventSerializers(serializers.ModelSerializer):
    class Meta:
        model=Event
        fields = [
                "id",
                "event_type",
                "payload",
                "created_at",
            ]
        read_only_fields = ["id", "created_at"]


class SubscriptionsSerializers(serializers.ModelSerializer):
    class Meta:
        model=Subscriptions
        fields = [
                "id",
                "endpoint",
                "event_type",
                "created_at",
            ]
        read_only_fields = ["id", "created_at"]