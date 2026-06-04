from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from .models import AuditLog


class PortalAccessTests(TestCase):
    def create_user(self, username, role, profile_active=True):
        user = User.objects.create_user(username=username, password='test-password')
        user.profile.role = role
        user.profile.is_active = profile_active
        user.profile.save(update_fields=['role', 'is_active'])
        return user

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('appointment_list'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('appointment_list')}",
        )

    def test_client_lands_on_own_profile_and_cannot_manage_users(self):
        user = self.create_user('client-user', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('portal_home'))
        self.assertRedirects(response, reverse('user_detail', args=[user.pk]))

        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)

    def test_provider_lands_on_appointments(self):
        user = self.create_user('provider-user', 'provider')
        self.client.force_login(user)

        response = self.client.get(reverse('portal_home'))

        self.assertRedirects(response, reverse('appointment_list'))

    def test_admin_can_manage_users(self):
        user = self.create_user('admin-user', 'admin')
        self.client.force_login(user)

        response = self.client.get(reverse('user_list'))

        self.assertEqual(response.status_code, 200)

    def test_profile_inactive_user_cannot_log_in(self):
        self.create_user('disabled-user', 'provider', profile_active=False)

        response = self.client.post(reverse('login'), {
            'username': 'disabled-user',
            'password': 'test-password',
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_register_creates_client_account_and_logs_user_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'new-client',
            'first_name': 'New',
            'last_name': 'Client',
            'email': 'new-client@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        user = User.objects.get(username='new-client')
        self.assertEqual(user.email, 'new-client@example.com')
        self.assertEqual(user.profile.role, 'client')
        self.assertTrue(user.profile.is_active)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertRedirects(response, reverse('portal_home'), fetch_redirect_response=False)

    def test_register_rejects_duplicate_email(self):
        self.create_user('existing-user', 'client')
        User.objects.filter(username='existing-user').update(email='same@example.com')

        response = self.client.post(reverse('register'), {
            'username': 'second-user',
            'first_name': 'Second',
            'last_name': 'User',
            'email': 'SAME@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='second-user').exists())
        self.assertContains(response, 'An account with this email already exists.')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_public_password_reset_sends_email(self):
        self.create_user('reset-user', 'client')
        User.objects.filter(username='reset-user').update(email='reset@example.com')

        response = self.client.post(reverse('password_reset'), {
            'email': 'reset@example.com',
        })

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reset your MyMoyo password', mail.outbox[0].subject)
        self.assertIn('/users/reset/', mail.outbox[0].body)

    def test_profile_disabled_during_session_loses_access(self):
        user = self.create_user('active-provider', 'provider')
        self.client.force_login(user)
        user.profile.is_active = False
        user.profile.save(update_fields=['is_active'])

        response = self.client.get(reverse('appointment_list'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('appointment_list')}",
        )

    def test_user_marked_for_password_change_is_redirected_until_updated(self):
        user = self.create_user('force-change-user', 'provider')
        user.profile.must_change_password = True
        user.profile.save(update_fields=['must_change_password'])

        response = self.client.post(reverse('login'), {
            'username': 'force-change-user',
            'password': 'test-password',
        })

        self.assertRedirects(response, reverse('password_change_required'))

        response = self.client.get(reverse('appointment_list'))
        self.assertRedirects(response, reverse('password_change_required'))

        response = self.client.post(reverse('password_change_required'), {
            'new_password1': 'ChangedStrongPass123!',
            'new_password2': 'ChangedStrongPass123!',
        })

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertRedirects(response, reverse('portal_home'), fetch_redirect_response=False)
        self.assertFalse(user.profile.must_change_password)
        self.assertTrue(user.check_password('ChangedStrongPass123!'))

    def test_user_can_update_theme_color(self):
        user = self.create_user('theme-user', 'provider')
        self.client.force_login(user)

        response = self.client.post(reverse('update_theme'), {
            'theme_color': 'indigo',
            'next': reverse('appointment_list'),
        })

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.theme_color, 'indigo')
        self.assertRedirects(response, reverse('appointment_list'))

    def test_admin_can_edit_user_with_management_modal_payload(self):
        admin = self.create_user('admin-editor', 'admin')
        user = self.create_user('old-username', 'client')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': 'new-username',
                'first_name': 'New',
                'last_name': 'Name',
                'email': 'new@example.com',
                'role': 'provider',
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertEqual(user.username, 'new-username')
        self.assertEqual(user.profile.role, 'provider')

        audit_log = AuditLog.objects.filter(
            action=AuditLog.ACTION_UPDATE,
            app_label='auth',
            model_name='user',
            object_pk=str(user.pk),
            actor=admin,
        ).latest('created_at')
        self.assertEqual(audit_log.changes['username'], {
            'old': 'old-username',
            'new': 'new-username',
        })

        response = self.client.get(reverse('object_history_events', args=['auth', 'user', user.pk]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        update_event = next(event for event in data['events'] if event['action'] == 'update')
        self.assertEqual(update_event['actor'], admin.username)
        self.assertEqual(update_event['actor_full_name'], '')
        self.assertIn({
            'field': 'username',
            'old': 'old-username',
            'new': 'new-username',
        }, update_event['changes'])

    def test_admin_can_make_user_inactive_with_management_modal_payload(self):
        admin = self.create_user('admin-deactivator', 'admin')
        user = self.create_user('active-user', 'client')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'client',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertFalse(user.is_active)
        self.assertFalse(user.profile.is_active)

    def test_admin_can_toggle_required_password_change_from_management(self):
        admin = self.create_user('change-toggle-admin', 'admin')
        user = self.create_user('change-toggle-user', 'client')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'client',
                'is_active': 'on',
                'must_change_password': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertTrue(user.profile.must_change_password)

    def test_manage_users_shows_logged_in_count_and_user_status(self):
        admin = self.create_user('online-admin', 'admin')
        online_user = self.create_user('online-user', 'provider')
        offline_user = self.create_user('offline-user', 'client')
        self.client.force_login(admin)
        other_client = Client()
        other_client.force_login(online_user)

        response = self.client.get(reverse('user_list'))

        users = {item['user'].username: item for item in response.context['users']}
        self.assertTrue(users[admin.username]['is_logged_in'])
        self.assertTrue(users[online_user.username]['is_logged_in'])
        self.assertFalse(users[offline_user.username]['is_logged_in'])
        self.assertContains(response, 'Logged In')
        self.assertContains(response, 'Logged Out')
        self.assertContains(response, f"openHistoryModal({admin.pk}, '{admin.username}')")
        self.assertContains(response, f"openResetPasswordModal({admin.pk}, '{admin.username}')")
        self.assertContains(response, 'Ask user to change password on first login')

        response = self.client.get(reverse('user_management_stats'))

        self.assertJSONEqual(response.content, {
            'total': 3,
            'active': 3,
            'inactive': 0,
            'logged_in': 2,
        })

    def test_async_user_search_highlights_matching_record_text(self):
        admin = self.create_user('highlight-admin', 'admin')
        user = self.create_user('clinic-user', 'provider')
        user.email = 'clinic@example.com'
        user.save(update_fields=['email'])
        self.client.force_login(admin)

        response = self.client.get(
            reverse('user_management_rows'),
            {'q': 'clin'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()['html']
        self.assertIn('<mark class="search-highlight">clin</mark>ic-user', html)
        self.assertIn('<mark class="search-highlight">clin</mark>ic@example.com', html)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_admin_can_reset_user_password_from_management(self):
        admin = self.create_user('password-admin', 'admin')
        user = self.create_user('reset-target', 'client')
        user.email = 'reset-target@example.com'
        user.save(update_fields=['email'])
        self.client.force_login(admin)
        target_client = Client()
        target_client.force_login(user)
        self.assertIn('_auth_user_id', target_client.session)

        response = self.client.post(
            reverse('user_reset_password', args=[user.pk]),
            {
                'must_change_password': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {
            'success': True,
            'email': 'reset-target@example.com',
            'sessions_invalidated': 1,
            'expires_in_minutes': 10,
        })
        self.assertFalse(user.check_password('test-password'))
        self.assertTrue(user.profile.must_change_password)
        self.assertIsNotNone(user.profile.temporary_password_expires_at)
        self.assertGreater(user.profile.temporary_password_expires_at, timezone.now())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Temporary password:', mail.outbox[0].body)
        self.assertIn('valid for 10 minutes', mail.outbox[0].body)
        temporary_password = mail.outbox[0].body.split('Temporary password: ')[1].splitlines()[0]
        self.assertTrue(user.check_password(temporary_password))
        self.assertNotIn('_auth_user_id', target_client.session)

        audit_log = AuditLog.objects.filter(
            action=AuditLog.ACTION_UPDATE,
            app_label='auth',
            model_name='user',
            object_pk=str(user.pk),
            actor=admin,
        ).latest('created_at')
        self.assertEqual(audit_log.changes['password'], {
            'old': '[redacted]',
            'new': '[redacted]',
        })

    def test_admin_password_reset_requires_user_email(self):
        admin = self.create_user('email-admin', 'admin')
        user = self.create_user('no-email-target', 'client')
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_reset_password', args=[user.pk]),
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['errors']['email'], ['This user does not have an email address.'])

    def test_expired_temporary_password_cannot_log_user_in(self):
        user = self.create_user('expired-temp-user', 'client')
        user.set_password('TempPass123!')
        user.save(update_fields=['password'])
        user.profile.must_change_password = True
        user.profile.temporary_password_expires_at = timezone.now() - timedelta(minutes=1)
        user.profile.save(update_fields=['must_change_password', 'temporary_password_expires_at'])

        response = self.client.post(reverse('login'), {
            'username': 'expired-temp-user',
            'password': 'TempPass123!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, 'This temporary password has expired.')

    def test_session_status_reports_reset_redirect_after_session_is_invalidated(self):
        user = self.create_user('status-target', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('session_status'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])

        self.client.session.flush()
        response = self.client.get(reverse('session_status'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['authenticated'])
        self.assertEqual(response.json()['login_url'], f"{reverse('login')}?password_reset=1")

    def test_logout_records_last_logout_timestamp(self):
        user = self.create_user('logout-user', 'provider')
        self.client.force_login(user)

        response = self.client.post(reverse('logout'))

        user.profile.refresh_from_db()
        self.assertRedirects(response, reverse('login'))
        self.assertIsNotNone(user.profile.last_logout)

    def test_auto_logout_returns_login_url_with_next_path(self):
        user = self.create_user('idle-user', 'provider')
        self.client.force_login(user)

        response = self.client.post(
            reverse('auto_logout'),
            {'next': '/users/appointments/?status=upcoming'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertIn('idle_timeout=1', response.json()['login_url'])
        self.assertIn('next=%2Fusers%2Fappointments%2F%3Fstatus%3Dupcoming', response.json()['login_url'])
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertIsNotNone(user.profile.last_logout)
