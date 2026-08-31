from django.urls import path
from .views import EndpointListClassView, EventListClassView, dashboard, SubscriptionClassView


urlpatterns = [
    path("endpoints/", EndpointListClassView.as_view(), name="endpoint-list-create"),
    path("events/", EventListClassView.as_view(),name="event-list-create"),
    path("dashboard/", dashboard, name="dashboard"),
    path("subscriptions/", SubscriptionClassView.as_view(), name="subscription-list-create"),
]
