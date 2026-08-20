from rest_framework import serializers
from .models import Endpoint

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
