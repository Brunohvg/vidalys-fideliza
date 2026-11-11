from django.test import TestCase
from django.urls import reverse

class HealthTests(TestCase):
    def test_liveness(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness(self):
        response = self.client.get(reverse("ready"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_requires_get(self):
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)
