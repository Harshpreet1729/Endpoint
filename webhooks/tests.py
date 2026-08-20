from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch, Mock

from webhooks.models import Endpoint, Event, Delivery, DeliveryAttempt
from webhooks.services.delivery import deliver_event, retry_delivery, MAX_ATTEMPTS
from webhooks.tasks import retry_delivery_task
import requests
# Create your tests here.

class DeliveryServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123"
        )

        self.endpoint = Endpoint.objects.create(
            name="Test Endpoint",
            url="https://example.com/webhook",
            secret="test-secret",
            owner=self.user
        )

        self.event = Event.objects.create(
            event_type="order.created",
            payload={"order_id": 1},
            owner=self.user
        )

    @patch("webhooks.services.delivery.requests.post")
    def test_deliver_event_success(self, mock_post):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_post.return_value = mock_response

        response = deliver_event(self.event, self.endpoint)

        self.assertEqual(response.status_code, 200)

        delivery = Delivery.objects.get(
            event=self.event,
            endpoint=self.endpoint
        )

        self.assertEqual(delivery.status, Delivery.Status.SUCCESS)
        self.assertEqual(delivery.attempt_count, 1)

        attempt = DeliveryAttempt.objects.get(delivery=delivery)

        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, DeliveryAttempt.Status.SUCCESS)

    @patch("webhooks.services.delivery.requests.post")
    def test_deliver_event_failure(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException(
            "Connection failed"
        )

        response = deliver_event(self.event, self.endpoint)

        self.assertIsNone(response)

        delivery = Delivery.objects.get(
            event=self.event,
            endpoint=self.endpoint
        )

        self.assertEqual(delivery.status, Delivery.Status.FAILED)
        self.assertIsNone(delivery.response_status_code)
        self.assertIn("Connection failed", delivery.response_body)

        attempt = DeliveryAttempt.objects.get(delivery=delivery)

        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, DeliveryAttempt.Status.FAILED)
        self.assertIsNone(attempt.response_status_code)

    @patch("webhooks.services.delivery.requests.post")
    def test_retry_delivery_reaches_max_attempts(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException(
            "Connection failed"
        )

        delivery = Delivery.objects.create(
            event=self.event,
            endpoint=self.endpoint,
            status=Delivery.Status.FAILED,
            attempt_count=4
        )

        response = retry_delivery(delivery)

        delivery.refresh_from_db()

        self.assertIsNone(response)
        self.assertEqual(delivery.attempt_count, MAX_ATTEMPTS)
        self.assertEqual(delivery.status, Delivery.Status.FAILED)

        attempt = DeliveryAttempt.objects.get(
            delivery=delivery,
            attempt_number=MAX_ATTEMPTS
        )

        self.assertEqual(attempt.status, DeliveryAttempt.Status.FAILED)

    @patch("webhooks.tasks.retry_delivery")
    def test_retry_task_marks_dead_lettered(self, mock_retry_delivery):
        delivery = Delivery.objects.create(
            event=self.event,
            endpoint=self.endpoint,
            status=Delivery.Status.FAILED,
            attempt_count=MAX_ATTEMPTS
        )

        retry_delivery_task.run(delivery.id)

        delivery.refresh_from_db()

        self.assertEqual(
            delivery.status,
            Delivery.Status.DEAD_LETTERED
        )