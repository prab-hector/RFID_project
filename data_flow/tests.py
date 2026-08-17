from django.test import TestCase
from django.urls import reverse
from users.models import Teammates, AttendanceLog, SystemState
from django.contrib.auth import get_user_model
import json

User = get_user_model()

class DataFlowViewsTests(TestCase):
    def test_process_rfid_master_card(self):
        url = reverse('process_rfid')
        response = self.client.post(
            url,
            data=json.dumps({'rfid_id': 'E25B2F45'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('admin_mode', response.json().get('status'))

    def test_process_rfid_unknown_card_creates_user(self):
        url = reverse('process_rfid')
        response = self.client.post(
            url,
            data=json.dumps({'rfid_id': 'NEWCARD1'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_export_attendance_log_valid_and_invalid_date(self):
        url = reverse('report')
        response = self.client.get(url, {'date': '2026-08-13'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        response_no_date = self.client.get(url)
        self.assertEqual(response_no_date.status_code, 200)

