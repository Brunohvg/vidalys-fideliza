from django.urls import path

from .views import OrderEventIngestView


urlpatterns = [
    path("events/orders/", OrderEventIngestView.as_view(), name="channel-order-events"),
]
