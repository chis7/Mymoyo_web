import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


class ChatbotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='chat-user', password='test-password')
        self.user.profile.role = 'provider'
        self.user.profile.save()

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 302)

    @override_settings(OPENAI_API_KEY='')
    def test_missing_api_key_uses_offline_local_content(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'How do appointments work?'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'offline')
        self.assertIn('Appointments', response.json()['reply'])
        self.assertIn(
            {'label': 'Appointments', 'url': reverse('appointment_list')},
            response.json()['links'],
        )

    @override_settings(OPENAI_API_KEY='')
    def test_admin_user_actions_are_available_offline(self):
        self.user.profile.role = 'admin'
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'How do I reset a user password?'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'offline')
        self.assertIn('temporary password', response.json()['reply'])
        self.assertIn('you can open Manage Users', response.json()['reply'])
        self.assertIn(
            {'label': 'Manage Users', 'url': reverse('user_list')},
            response.json()['links'],
        )

    @override_settings(OPENAI_API_KEY='')
    def test_non_admin_does_not_receive_manage_users_link(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'How do I search and edit users?'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'offline')
        self.assertIn('Manage Users', response.json()['reply'])
        self.assertIn('admin-only', response.json()['reply'])
        self.assertNotIn(
            {'label': 'Manage Users', 'url': reverse('user_list')},
            response.json()['links'],
        )

    @override_settings(OPENAI_API_KEY='test-key', OPENAI_CHATBOT_MODEL='test-model')
    @patch('chatbot.views.urlopen')
    def test_online_prompt_includes_current_role_permissions(self, mock_urlopen):
        self.client.force_login(self.user)
        response_body = json.dumps({
            'output': [{
                'content': [{
                    'type': 'output_text',
                    'text': 'Ask an administrator to update user accounts.',
                }],
            }],
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = BytesIO(response_body)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'Can I delete a user?'}),
            content_type='application/json',
        )

        request_payload = json.loads(mock_urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Current user\'s role and permissions', request_payload['instructions'])
        self.assertIn('Can manage users: no', request_payload['instructions'])

    @override_settings(OPENAI_API_KEY='test-key', OPENAI_CHATBOT_MODEL='test-model')
    @patch('chatbot.views.urlopen')
    def test_returns_assistant_reply(self, mock_urlopen):
        self.client.force_login(self.user)
        response_body = json.dumps({
            'output': [{
                'content': [{
                    'type': 'output_text',
                    'text': 'How can I help?',
                }],
            }],
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = BytesIO(response_body)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reply'], 'How can I help?')
        self.assertEqual(response.json()['mode'], 'online')
        self.assertEqual(response.json()['links'], [])

    @override_settings(OPENAI_API_KEY='test-key', OPENAI_CHATBOT_MODEL='test-model')
    @patch('chatbot.views.urlopen', side_effect=TimeoutError)
    def test_online_error_falls_back_to_offline_local_content(self, mock_urlopen):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('chatbot_message'),
            data=json.dumps({'message': 'Tell me about side effects'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'offline')
        self.assertIn('side effects', response.json()['reply'])
        self.assertIn(
            {'label': 'Find a Clinic', 'url': reverse('facility_map')},
            response.json()['links'],
        )
