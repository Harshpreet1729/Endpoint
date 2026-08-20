from django.urls import path
from .views import EndpointListClassView, EventListClassView

urlpatterns = [
    path("endpoints/", EndpointListClassView.as_view(), name="endpoint-list-create"),
    path("events/", EventListClassView.as_view(),name="event-list-create"),
]
