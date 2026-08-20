from django.urls import path
from .views import EndpointListClassView

urlpatterns = [
    path("endpoints/", EndpointListClassView.as_view(), name="endpoint-list-create")
]

