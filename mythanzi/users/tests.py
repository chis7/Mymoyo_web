from datetime import timedelta
from datetime import date

from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from .forms import ClientAppointmentForm
from .models import (
    Appointment,
    AuditLog,
    ClientConsent,
    ClientJourneyEvent,
    ClientLocator,
    ClinicFeedbackSubmission,
    FollowUpTask,
    PopulationGroup,
    ReferralRecord,
    SelfRiskAssessmentSubmission,
    SelfTestReportSubmission,
    SideEffectReportSubmission,
)
from locations.models import District, Facility, Province, Service


class ClientManagementModelTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create_user(username='worker', password='test-password')
        self.worker.profile.role = 'provider'
        self.worker.profile.save(update_fields=['role'])
        self.client_user = User.objects.create_user(username='client', password='test-password')
        self.client_user.profile.role = 'client'
        self.client_user.profile.save(update_fields=['role'])

    def test_client_management_records_link_to_client(self):
        locator = ClientLocator.objects.create(
            client=self.client_user,
            mobiliser_zone='Zone A',
            preferred_contact_method='sms',
            updated_by=self.worker,
        )
        journey = ClientJourneyEvent.objects.create(
            client=self.client_user,
            stage='risk_assessment',
            outcome='completed',
            recorded_by=self.worker,
        )
        referral = ReferralRecord.objects.create(
            client=self.client_user,
            receiving_hub='Central Hub',
            confirmation_status='attended',
            recorded_by=self.worker,
        )
        task = FollowUpTask.objects.create(
            client=self.client_user,
            assigned_to=self.worker,
            reason='tracing',
            due_date=timezone.localdate(),
            created_by=self.worker,
        )
        consent = ClientConsent.objects.create(
            client=self.client_user,
            consent_to_follow_up=True,
            recorded_by=self.worker,
        )

        self.assertEqual(locator.client, self.client_user)
        self.assertEqual(journey.get_stage_display(), 'Risk assessment')
        self.assertEqual(referral.get_confirmation_status_display(), 'Attended')
        self.assertEqual(task.get_reason_display(), 'Tracing')
        self.assertTrue(consent.consent_to_follow_up)

    def test_referral_code_and_not_attended_follow_up_are_created(self):
        mobiliser = User.objects.create_user(username='mobiliser', password='test-password')
        mobiliser.profile.role = 'mobiliser'
        mobiliser.profile.save(update_fields=['role'])

        referral = ReferralRecord.objects.create(
            client=self.client_user,
            receiving_hub='Central Hub',
            assigned_mobiliser=mobiliser,
            confirmation_status='not_attended',
            recorded_by=self.worker,
        )

        self.assertTrue(referral.referral_code.startswith('REF-'))
        task = self.client_user.follow_up_tasks.get(reason='referral_confirmation')
        self.assertEqual(task.assigned_to, mobiliser)
        self.assertIn(referral.referral_code, task.notes)


class PortalAccessTests(TestCase):
    def create_user(self, username, role, profile_active=True):
        user = User.objects.create_user(username=username, password='test-password')
        user.profile.role = role
        user.profile.is_active = profile_active
        user.profile.save(update_fields=['role', 'is_active'])
        return user

    def create_facility(self):
        province = Province.objects.create(name='Lusaka')
        district = District.objects.create(name='Lusaka', province=province)
        facility = Facility.objects.create(name='Central Clinic', district=district)
        service, _ = Service.objects.get_or_create(
            code='follow_up',
            defaults={'name': 'Follow-up Visit'},
        )
        facility.services.add(service)
        return province, district, facility

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
        self.assertRedirects(response, '/app/', fetch_redirect_response=False)

        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)

    def test_provider_lands_on_appointments(self):
        user = self.create_user('provider-user', 'provider')
        self.client.force_login(user)

        response = self.client.get(reverse('portal_home'))

        self.assertRedirects(response, reverse('client_management'), fetch_redirect_response=False)

    def test_admin_lands_on_dashboard(self):
        user = self.create_user('dashboard-admin', 'admin')
        self.client.force_login(user)

        response = self.client.get(reverse('portal_home'))

        self.assertRedirects(response, reverse('user_dashboard'), fetch_redirect_response=False)

    def test_provider_next_dashboard_falls_back_to_allowed_landing(self):
        user = self.create_user('provider-next-dashboard', 'provider')
        response = self.client.post(reverse('login'), {
            'username': user.username,
            'password': 'test-password',
            'next': reverse('user_dashboard'),
        })

        self.assertRedirects(response, reverse('client_management'), fetch_redirect_response=False)

    def test_referral_scan_access_allows_only_receiving_facility_staff(self):
        from .views import can_open_referral_scan

        receiving_facility = self.create_facility()
        other_facility = Facility.objects.create(name='Other Clinic', district=receiving_facility.district)
        client_user = self.create_user('scan-client', 'client')
        provider = self.create_user('scan-provider', 'provider')
        provider.profile.facility = receiving_facility
        provider.profile.save(update_fields=['facility'])
        referral = ReferralRecord.objects.create(
            client=client_user,
            receiving_facility=receiving_facility,
            recorded_by=provider,
        )

        self.assertTrue(can_open_referral_scan(provider, referral))

        provider.profile.facility = other_facility
        provider.profile.save(update_fields=['facility'])
        provider.profile.refresh_from_db()
        self.assertFalse(can_open_referral_scan(provider, referral))

    def test_referral_scan_returns_gibberish_for_anonymous_user(self):
        receiving_facility = self.create_facility()
        client_user = self.create_user('anonymous-scan-client', 'client')
        referral = ReferralRecord.objects.create(
            client=client_user,
            receiving_facility=receiving_facility,
        )

        response = self.client.get(reverse('referral_scan', kwargs={'referral_code': referral.referral_code}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertNotContains(response, referral.referral_code)

    def test_admin_can_manage_users(self):
        user = self.create_user('admin-user', 'admin')
        self.client.force_login(user)

        response = self.client.get(reverse('user_list'))

        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_can_view_notification_engine(self):
        user = self.create_user('reminder-user', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('medication_reminders'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Notifications Engine')
        self.assertContains(response, 'Medication Dose')
        self.assertContains(response, 'Appointment')

    def test_anonymous_user_is_redirected_from_medication_reminders(self):
        response = self.client.get(reverse('medication_reminders'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('medication_reminders')}",
        )

    def test_authenticated_user_can_view_self_risk_assessment(self):
        user = self.create_user('screening-user', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('self_risk_assessment'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Self-Risk Screening')
        self.assertContains(response, 'When was your most recent HIV test?')
        self.assertContains(response, 'Find a Clinic')
        self.assertContains(response, 'data-wizard-page')

    def test_self_risk_assessment_returns_guidance(self):
        user = self.create_user('high-risk-screening-user', 'client')
        self.client.force_login(user)

        response = self.client.post(reverse('self_risk_assessment'), {
            'recent_test': 'never',
            'partners': '5_plus',
            'condom_use': 'rarely',
            'partner_status': 'yes',
            'sti_symptoms': 'yes',
            'prep_use': 'no',
            'pregnancy_or_breastfeeding': 'no',
            'safety_concerns': 'no',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Higher risk')
        self.assertContains(response, 'Recommended next steps')
        self.assertContains(response, 'Book or visit a clinic')
        submission = SelfRiskAssessmentSubmission.objects.get(user=user)
        self.assertEqual(submission.level, 'Higher')
        self.assertEqual(submission.answers['recent_test'], 'never')

    def test_anonymous_user_can_use_self_risk_assessment(self):
        response = self.client.get(reverse('self_risk_assessment'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Self-Risk Screening')

    def test_authenticated_user_can_view_self_test_report(self):
        user = self.create_user('self-test-user', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('self_test_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent Self-Test')
        self.assertContains(response, 'What type of self-test did you use?')
        self.assertContains(response, 'Find a Clinic')
        self.assertContains(response, 'data-wizard-page')

    def test_self_test_report_returns_positive_result_guidance(self):
        user = self.create_user('reactive-self-test-user', 'client')
        self.client.force_login(user)

        response = self.client.post(reverse('self_test_report'), {
            'test_type': 'oral_fluid',
            'kit_source': 'clinic',
            'test_date': date.today().isoformat(),
            'result': 'positive',
            'followed_instructions': 'yes',
            'confirmatory_test': 'no',
            'support_needed': 'yes',
            'notes': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirm at clinic')
        self.assertContains(response, 'Confirmatory testing is still needed')
        self.assertContains(response, 'Recommended next steps')
        submission = SelfTestReportSubmission.objects.get(user=user)
        self.assertEqual(submission.result, 'positive')
        self.assertEqual(submission.answers['test_date'], date.today().isoformat())

    def test_self_test_report_rejects_future_test_date(self):
        user = self.create_user('future-self-test-user', 'client')
        self.client.force_login(user)

        future_date = timezone.localdate() + timedelta(days=1)
        response = self.client.post(reverse('self_test_report'), {
            'test_type': 'finger_prick',
            'kit_source': 'chw',
            'test_date': future_date.isoformat(),
            'result': 'negative',
            'followed_instructions': 'yes',
            'confirmatory_test': 'no',
            'support_needed': 'no',
            'notes': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test date cannot be in the future.')

    def test_anonymous_user_can_use_self_test_report(self):
        response = self.client.get(reverse('self_test_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent Self-Test')

    def test_authenticated_user_can_view_side_effect_report(self):
        user = self.create_user('side-effect-user', 'client')
        self.client.force_login(user)

        response = self.client.get(reverse('side_effect_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Report Side Effects')
        self.assertContains(response, 'Which prevention medicine or product are you using?')
        self.assertContains(response, 'Find a Clinic')
        self.assertContains(response, 'data-wizard-page')

    def test_side_effect_report_returns_urgent_guidance(self):
        user = self.create_user('urgent-side-effect-user', 'client')
        self.client.force_login(user)

        response = self.client.post(reverse('side_effect_report'), {
            'prevention_method': 'lenacapavir',
            'symptom_start_date': timezone.localdate().isoformat(),
            'symptoms': 'Severe rash and swelling',
            'severity': 'severe',
            'status': 'worse',
            'urgent_symptoms': 'yes',
            'stopped_medicine': 'yes',
            'facility_visit': 'no',
            'support_needed': 'yes',
            'contact_preference': 'Phone',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Urgent care')
        self.assertContains(response, 'Seek urgent care now')
        self.assertContains(response, 'Tell a provider you stopped or missed medicine')
        submission = SideEffectReportSubmission.objects.get(user=user)
        self.assertEqual(submission.severity, 'severe')
        self.assertTrue(submission.follow_up_requested)

    def test_side_effect_report_rejects_future_symptom_date(self):
        user = self.create_user('future-side-effect-user', 'client')
        self.client.force_login(user)

        future_date = timezone.localdate() + timedelta(days=1)
        response = self.client.post(reverse('side_effect_report'), {
            'prevention_method': 'oral_prep',
            'symptom_start_date': future_date.isoformat(),
            'symptoms': 'Nausea',
            'severity': 'mild',
            'status': 'ongoing',
            'urgent_symptoms': 'no',
            'stopped_medicine': 'no',
            'facility_visit': 'no',
            'support_needed': 'no',
            'contact_preference': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Symptom start date cannot be in the future.')

    def test_anonymous_user_can_use_side_effect_report(self):
        response = self.client.get(reverse('side_effect_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Report Side Effects')

    def create_facility(self):
        province = Province.objects.create(name='Lusaka')
        district = District.objects.create(name='Lusaka', province=province)
        facility = Facility.objects.create(
            name='Central Clinic',
            district=district,
            level='Primary',
        )
        service, _ = Service.objects.get_or_create(
            code='follow_up',
            defaults={'name': 'Follow-up Visit'},
        )
        facility.services.add(service)
        return facility

    def create_location(self):
        facility = self.create_facility()
        return facility.district.province, facility.district, facility

    def test_authenticated_user_can_view_clinic_feedback(self):
        user = self.create_user('feedback-user', 'client')
        facility = self.create_facility()
        self.client.force_login(user)

        response = self.client.get(reverse('clinic_feedback'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rate Clinic Services')
        self.assertContains(response, 'Which clinic did you visit?')
        self.assertContains(response, facility.name)
        self.assertContains(response, 'data-wizard-page')
        self.assertContains(response, 'data-star-rating')

    def test_clinic_feedback_returns_review_guidance(self):
        user = self.create_user('low-feedback-user', 'client')
        facility = self.create_facility()
        self.client.force_login(user)

        response = self.client.post(reverse('clinic_feedback'), {
            'facility': facility.pk,
            'visit_date': timezone.localdate().isoformat(),
            'visit_reason': 'prep',
            'overall_rating': '2',
            'wait_time_rating': '1',
            'staff_respect_rating': '2',
            'medicine_availability': 'no',
            'would_recommend': 'no',
            'follow_up_needed': 'yes',
            'comments': 'Long wait and no medicine available.',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Needs review')
        self.assertContains(response, 'Waiting time was rated low')
        self.assertContains(response, 'Follow-up was requested')
        submission = ClinicFeedbackSubmission.objects.get(user=user)
        self.assertEqual(submission.facility, facility)
        self.assertEqual(str(submission.average_rating), '1.7')
        self.assertTrue(submission.follow_up_requested)

    def test_clinic_feedback_rejects_future_visit_date(self):
        user = self.create_user('future-feedback-user', 'client')
        facility = self.create_facility()
        self.client.force_login(user)

        future_date = timezone.localdate() + timedelta(days=1)
        response = self.client.post(reverse('clinic_feedback'), {
            'facility': facility.pk,
            'visit_date': future_date.isoformat(),
            'visit_reason': 'testing',
            'overall_rating': '5',
            'wait_time_rating': '5',
            'staff_respect_rating': '5',
            'medicine_availability': 'yes',
            'would_recommend': 'yes',
            'follow_up_needed': 'no',
            'comments': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visit date cannot be in the future.')

    def test_anonymous_user_can_use_clinic_feedback(self):
        facility = self.create_facility()
        response = self.client.get(reverse('clinic_feedback'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rate Clinic Services')
        self.assertContains(response, facility.name)

    def test_anonymous_submissions_are_claimed_after_registration(self):
        self.create_facility()
        response = self.client.post(reverse('self_risk_assessment'), {
            'recent_test': 'never',
            'partners': '5_plus',
            'condom_use': 'rarely',
            'partner_status': 'yes',
            'sti_symptoms': 'yes',
            'prep_use': 'no',
            'pregnancy_or_breastfeeding': 'no',
            'safety_concerns': 'no',
        })
        self.assertEqual(response.status_code, 200)
        submission = SelfRiskAssessmentSubmission.objects.get()
        self.assertIsNone(submission.user)

        response = self.client.post(reverse('register'), {
            'username': 'claiming-client',
            'first_name': 'Claiming',
            'last_name': 'Client',
            'email': 'claiming@example.com',
            'phone': '+260955000000',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.user.username, 'claiming-client')

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
            'phone': '+260977000001',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        user = User.objects.get(username='new-client')
        self.assertEqual(user.email, 'new-client@example.com')
        self.assertEqual(user.profile.phone, '+260977000001')
        self.assertEqual(user.profile.role, 'client')
        self.assertTrue(user.profile.is_active)
        self.assertTrue(user.profile.is_phone_verified)
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
            'phone': '+260977000002',
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
        self.assertIn('Reset your MyThanzi password', mail.outbox[0].subject)
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

    def test_upcoming_appointments_are_future_scheduled_visits(self):
        provider = self.create_user('calendar-provider', 'provider')
        beneficiary = self.create_user('calendar-client', 'client')
        province, district, facility = self.create_location()
        now = timezone.localtime()
        past = now - timedelta(hours=1)
        future = now + timedelta(days=1)

        Appointment.objects.create(
            beneficiary=beneficiary,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=past.date(),
            appointment_time=past.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )
        future_appointment = Appointment.objects.create(
            beneficiary=beneficiary,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )

        self.client.force_login(provider)
        response = self.client.get(reverse('appointment_list'), {
            'status': 'upcoming',
            'month': future.strftime('%Y-%m'),
        })

        self.assertContains(response, future_appointment.beneficiary.username)
        self.assertEqual(response.context['month_appointment_count'], 1)

    def test_appointment_booking_rejects_past_datetime(self):
        provider = self.create_user('past-booking-provider', 'provider')
        beneficiary = self.create_user('past-booking-client', 'client')
        province, district, facility = self.create_location()
        past = timezone.localtime() - timedelta(hours=1)
        self.client.force_login(provider)

        response = self.client.post(reverse('appointment_list'), {
            'client': beneficiary.pk,
            'visit_purpose': 'follow_up',
            'appointment_date': past.date().isoformat(),
            'appointment_time': past.strftime('%H:%M'),
            'facility': facility.pk,
            'notes': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Appointments cannot be booked in the past.')
        self.assertFalse(Appointment.objects.filter(beneficiary=beneficiary).exists())

    def test_provider_books_appointment_by_client_name_selection(self):
        provider = self.create_user('reference-booking-provider', 'provider')
        beneficiary = self.create_user('reference-booking-client', 'client')
        province, district, facility = self.create_location()
        future = timezone.localtime() + timedelta(days=1)
        self.client.force_login(provider)

        response = self.client.post(reverse('appointment_list'), {
            'client': beneficiary.pk,
            'visit_purpose': 'follow_up',
            'appointment_date': future.date().isoformat(),
            'appointment_time': future.strftime('%H:%M'),
            'facility': facility.pk,
            'notes': 'Bring records.',
        })

        appointment = Appointment.objects.get(beneficiary=beneficiary)
        self.assertRedirects(response, reverse('appointment_list'))
        self.assertEqual(appointment.created_by, provider)
        self.assertEqual(appointment.notes, 'Bring records.')

    def test_facility_user_sees_created_and_facility_appointments(self):
        provider = self.create_user('own-appointments-provider', 'provider')
        other_provider = self.create_user('other-appointments-provider', 'provider')
        beneficiary = self.create_user('own-appointments-client', 'client')
        facility_beneficiary = self.create_user('facility-appointments-client', 'client')
        hidden_beneficiary = self.create_user('other-appointments-client', 'client')
        province, district, facility = self.create_location()
        other_province = Province.objects.create(name='Copperbelt')
        other_district = District.objects.create(name='Ndola', province=other_province)
        other_facility = Facility.objects.create(name='Ndola Clinic', district=other_district)
        provider.profile.facility = facility
        provider.profile.save(update_fields=['facility'])
        future = timezone.localtime() + timedelta(days=1)

        visible_appointment = Appointment.objects.create(
            beneficiary=beneficiary,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )
        facility_appointment = Appointment.objects.create(
            beneficiary=facility_beneficiary,
            created_by=other_provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )
        hidden_appointment = Appointment.objects.create(
            beneficiary=hidden_beneficiary,
            created_by=other_provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=other_province,
            district=other_district,
            facility=other_facility,
            status='upcoming',
        )

        self.client.force_login(provider)
        response = self.client.get(reverse('appointment_list'), {
            'month': future.strftime('%Y-%m'),
        })

        self.assertContains(response, visible_appointment.beneficiary.username)
        self.assertContains(response, facility_appointment.beneficiary.username)
        self.assertNotContains(response, hidden_appointment.beneficiary.username)
        self.assertEqual(response.context['month_appointment_count'], 2)

    def test_client_only_sees_own_appointments_labeled_by_facility(self):
        client = self.create_user('client-calendar-user', 'client')
        other_client = self.create_user('client-calendar-other', 'client')
        provider = self.create_user('client-calendar-provider', 'provider')
        province, district, facility = self.create_location()
        future = timezone.localtime() + timedelta(days=1)

        Appointment.objects.create(
            beneficiary=client,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )
        Appointment.objects.create(
            beneficiary=other_client,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )

        self.client.force_login(client)
        response = self.client.get(reverse('appointment_list'), {
            'month': future.strftime('%Y-%m'),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, facility.name)
        self.assertNotContains(response, other_client.username)
        self.assertNotContains(response, f'- {client.username}')
        self.assertFalse(response.context['can_manage_appointments'])
        self.assertEqual(response.context['month_appointment_count'], 1)

    def test_admin_sees_all_appointments(self):
        admin = self.create_user('all-appointments-admin', 'admin')
        provider = self.create_user('all-appointments-provider', 'provider')
        other_provider = self.create_user('all-appointments-other-provider', 'provider')
        beneficiary = self.create_user('all-appointments-client', 'client')
        other_beneficiary = self.create_user('all-appointments-other-client', 'client')
        province, district, facility = self.create_location()
        future = timezone.localtime() + timedelta(days=1)

        Appointment.objects.create(
            beneficiary=beneficiary,
            created_by=provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )
        Appointment.objects.create(
            beneficiary=other_beneficiary,
            created_by=other_provider,
            visit_purpose='follow_up',
            appointment_date=future.date(),
            appointment_time=future.time(),
            province=province,
            district=district,
            facility=facility,
            status='upcoming',
        )

        self.client.force_login(admin)
        response = self.client.get(reverse('appointment_list'), {
            'month': future.strftime('%Y-%m'),
        })

        self.assertContains(response, beneficiary.username)
        self.assertContains(response, other_beneficiary.username)
        self.assertEqual(response.context['month_appointment_count'], 2)

    def test_admin_can_edit_user_with_management_modal_payload(self):
        admin = self.create_user('admin-editor', 'admin')
        user = self.create_user('old-username', 'client')
        _province, _district, facility = self.create_location()
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': 'new-username',
                'first_name': 'New',
                'last_name': 'Name',
                'email': 'new@example.com',
                'role': 'provider',
                'facility': facility.pk,
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertEqual(user.username, 'new-username')
        self.assertEqual(user.profile.role, 'provider')
        self.assertEqual(user.profile.facility_id, facility.pk)

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

    def test_supervisor_facility_mapping_persists(self):
        admin = self.create_user('facility-admin', 'admin')
        user = self.create_user('facility-supervisor', 'supervisor')
        _province, _district, facility = self.create_location()
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'supervisor',
                'facility': facility.pk,
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertEqual(user.profile.facility_id, facility.pk)

    def test_client_facility_mapping_is_cleared(self):
        admin = self.create_user('client-facility-admin', 'admin')
        user = self.create_user('client-with-facility', 'provider')
        _province, _district, facility = self.create_location()
        user.profile.facility = facility
        user.profile.save(update_fields=['facility'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'client',
                'facility': facility.pk,
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertIsNone(user.profile.facility_id)

    def test_admin_can_assign_population_group_to_client(self):
        admin = self.create_user('population-admin', 'admin')
        user = self.create_user('population-client', 'client')
        group = PopulationGroup.objects.create(name='FSW', code='fsw', is_active=True)
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'client',
                'population_group': group.pk,
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertEqual(user.profile.population_group_id, group.pk)

    def test_population_group_is_cleared_for_non_client_roles(self):
        admin = self.create_user('population-clear-admin', 'admin')
        user = self.create_user('population-worker', 'client')
        group = PopulationGroup.objects.create(name='General Population', code='general-population', is_active=True)
        _province, _district, facility = self.create_location()
        user.profile.population_group = group
        user.profile.save(update_fields=['population_group'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('user_edit', args=[user.pk]),
            {
                'username': user.username,
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'provider',
                'facility': facility.pk,
                'population_group': group.pk,
                'is_active': 'on',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        user.profile.refresh_from_db()
        self.assertJSONEqual(response.content, {'success': True})
        self.assertIsNone(user.profile.population_group_id)

    def test_admin_can_manage_population_groups(self):
        admin = self.create_user('population-page-admin', 'admin')
        self.client.force_login(admin)

        response = self.client.post(reverse('population_group_management'), {
            'name': 'General Population',
            'code': 'general-population',
            'description': 'Default client group',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('population_group_management'))
        self.assertTrue(PopulationGroup.objects.filter(code='general-population').exists())

    def test_client_journey_events_can_be_recorded_for_my_journey(self):
        client = self.create_user('journey-client', 'client')
        event = ClientJourneyEvent.objects.create(
            client=client,
            stage='risk_assessment',
            outcome='completed',
            recorded_by=client,
        )

        self.assertEqual(client.journey_events.get(), event)

    def test_client_record_appointment_form_creates_client_appointment(self):
        provider = self.create_user('client-record-provider', 'provider')
        client = self.create_user('client-record-client', 'client')
        _province, _district, facility = self.create_location()
        provider.profile.facility = facility
        provider.profile.save(update_fields=['facility'])
        future = timezone.localtime() + timedelta(days=1)

        form = ClientAppointmentForm(
            {
                'visit_purpose': 'follow_up',
                'appointment_date': future.date().isoformat(),
                'appointment_time': future.strftime('%H:%M'),
                'facility': facility.pk,
                'notes': 'Created from client management.',
            },
            client=client,
            created_by=provider,
        )

        self.assertTrue(form.is_valid(), form.errors)
        appointment = form.save()
        self.assertEqual(appointment.created_by, provider)
        self.assertEqual(appointment.facility, facility)

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
