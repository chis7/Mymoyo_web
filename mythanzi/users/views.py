import base64
import calendar
import csv
import io
import json
import logging
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.apps import apps
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.forms import formset_factory
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .models import (
    Appointment,
    AuditLog,
    ClientConsent,
    ClientExitInterview,
    ClinicFeedbackSubmission,
    ClientLocator,
    GrievanceCase,
    Notification,
    NotificationTypeSetting,
    PersonIdentity,
    PopulationGroup,
    ReferralRecord,
    SafeguardingCase,
    SelfRiskAssessmentSubmission,
    SelfTestReportSubmission,
    SideEffectReportSubmission,
    UserProfile,
)
from .audit import should_audit_model
from .notifications import notify_appointment_created
from .forms import (
    AppointmentForm,
    AppointmentEditForm,
    ClientConsentForm,
    ClientExitInterviewForm,
    ClientAppointmentForm,
    ClinicFeedbackForm,
    ClientJourneyEventForm,
    ClientLocatorForm,
    FACILITY_ASSIGNABLE_ROLES,
    FACILITY_REQUIRED_ROLES,
    FollowUpTaskForm,
    GrievanceCaseUpdateForm,
    GrievanceSubmissionForm,
    PopulationGroupForm,
    PublicRegistrationForm,
    ReferralConfirmationForm,
    ReferralRecordForm,
    SafeguardingCaseUpdateForm,
    SafeguardingReportForm,
    SideEffectReportForm,
    SelfProfileForm,
    SelfRiskAssessmentForm,
    SelfTestReportForm,
    UserForm,
    UserProfileForm,
    UserCreationForm,
)
from .access import (
    APPOINTMENT_ROLES,
    DASHBOARD_ROLES,
    USER_ADMIN_ROLES,
    active_login_required,
    can_manage_appointments,
    get_user_role,
    role_required,
    visible_appointment_filter,
)
from locations.models import District, Facility, Province, Service


logger = logging.getLogger(__name__)
TEMPORARY_PASSWORD_TTL = timedelta(minutes=10)
ACCOUNT_OTP_TTL = timedelta(minutes=10)
ClientJourneyEventFormSet = formset_factory(ClientJourneyEventForm, extra=3, max_num=10)

CLIENT_BULK_UPLOAD_SPECS = {
    'journey-events': {
        'label': 'Journey Events',
        'filename': 'journey-events-template.csv',
        'fields': ['stage', 'event_date', 'outcome', 'notes'],
        'form_class': ClientJourneyEventForm,
        'help_text': (
            'Use stage values: contact, risk_assessment, referral, hivst, prep_len_initiation, '
            'follow_up, continuation. Dates must use YYYY-MM-DD.'
        ),
    },
    'referrals': {
        'label': 'Referrals',
        'filename': 'referrals-template.csv',
        'fields': [
            'receiving_facility',
            'assigned_mobiliser',
            'confirmation_status',
            'initiation_outcome',
            'referred_on',
            'notes',
        ],
        'form_class': ReferralRecordForm,
        'help_text': (
            'receiving_facility can be a facility id, code, or exact facility name. assigned_mobiliser is optional username. '
            'Use confirmation_status values: generated, sent, received, attended, initiated, not_attended, closed. '
            'Use initiation_outcome values: pending, len_prep_initiated, hivst_received, referred_elsewhere, declined.'
        ),
    },
    'follow-ups': {
        'label': 'Follow-Up Tasks',
        'filename': 'follow-up-tasks-template.csv',
        'fields': ['assigned_to', 'reason', 'status', 'priority', 'due_date', 'notes', 'outcome_notes'],
        'form_class': FollowUpTaskForm,
        'help_text': (
            'assigned_to is optional and should be a username when provided. '
            'Use reason/status/priority choice values exactly as shown in the template.'
        ),
    },
    'appointments': {
        'label': 'Appointments',
        'filename': 'appointments-template.csv',
        'fields': ['visit_purpose', 'appointment_date', 'appointment_time', 'facility', 'notes'],
        'form_class': ClientAppointmentForm,
        'help_text': (
            'facility can be a facility id, code, or exact facility name. appointment_time must use HH:MM.'
        ),
    },
}

DEFAULT_NOTIFICATION_TYPE_SETTINGS = [
    {
        'key': 'medication_dose',
        'name': 'Medication Dose',
        'description': 'Daily medicine, PrEP, LEN, or other prevention product reminders.',
        'cadence': 'daily',
        'channel': 'portal',
        'timing': '08:00',
    },
    {
        'key': 'appointment',
        'name': 'Appointment',
        'description': 'Upcoming clinic, review, initiation, injection, or refill visits.',
        'cadence': 'before_event',
        'channel': 'portal_email',
        'timing': '24h',
    },
    {
        'key': 'medication_refill',
        'name': 'Medication Refill',
        'description': 'Refill collection and stock continuity reminders.',
        'cadence': 'before_event',
        'channel': 'portal',
        'timing': '72h',
    },
    {
        'key': 'lab_collection',
        'name': 'Lab Collection',
        'description': 'Lab sample collection and result follow-up reminders.',
        'cadence': 'before_event',
        'channel': 'portal',
        'timing': '24h',
    },
    {
        'key': 'referral_follow_up',
        'name': 'Referral Follow-Up',
        'description': 'Reminders to confirm attendance, linkage, and referral outcomes.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': '48h',
    },
    {
        'key': 'side_effect_check_in',
        'name': 'Side-Effect Check-In',
        'description': 'Safety and tolerability check-ins after initiation or product changes.',
        'cadence': 'after_event',
        'channel': 'portal',
        'timing': '7d',
    },
]


def get_client_bulk_upload_spec(kind):
    spec = CLIENT_BULK_UPLOAD_SPECS.get(kind)
    if not spec:
        raise PermissionDenied('Unknown bulk upload type.')
    return spec


def get_client_bulk_session_key(client, kind):
    return f'client_bulk_upload:{client.pk}:{kind}'


def get_client_bulk_template_rows(kind):
    next_week = timezone.localdate() + timedelta(days=7)
    today = timezone.localdate()
    if kind == 'journey-events':
        return [{
            'stage': 'contact',
            'event_date': today.isoformat(),
            'outcome': 'completed',
            'notes': 'Initial contact completed',
        }]
    if kind == 'referrals':
        facility = Facility.objects.order_by('name').first()
        return [{
            'receiving_facility': facility.code or facility.name if facility else '',
            'assigned_mobiliser': '',
            'confirmation_status': 'generated',
            'initiation_outcome': 'pending',
            'referred_on': today.isoformat(),
            'notes': 'Referral generated',
        }]
    if kind == 'follow-ups':
        return [{
            'assigned_to': '',
            'reason': 'tracing',
            'status': 'open',
            'priority': 'normal',
            'due_date': next_week.isoformat(),
            'notes': 'Follow up with client',
            'outcome_notes': '',
        }]
    if kind == 'appointments':
        facility = Facility.objects.order_by('name').first()
        return [{
            'visit_purpose': 'follow_up',
            'appointment_date': next_week.isoformat(),
            'appointment_time': '09:00',
            'facility': facility.code or facility.name if facility else '',
            'notes': 'Routine follow-up appointment',
        }]
    return []


def resolve_bulk_assigned_user(value):
    if not value:
        return '', None
    assigned_to = User.objects.filter(username__iexact=value).first()
    if not assigned_to:
        return value, f'No active user was found for assigned_to "{value}".'
    return str(assigned_to.pk), None


def resolve_bulk_facility(value):
    if not value:
        return '', 'Facility is required.'
    facility_filter = Q(code__iexact=value) | Q(name__iexact=value)
    if value.isdigit():
        facility_filter |= Q(pk=int(value))
    facility = Facility.objects.filter(facility_filter).first()
    if not facility:
        return value, f'No facility was found for "{value}". Use a facility id, code, or exact name.'
    return str(facility.pk), None


def normalize_client_bulk_row(kind, row, fields):
    normalized = {field: (row.get(field) or '').strip() for field in fields}
    errors = []
    if kind == 'follow-ups':
        normalized['assigned_to'], error = resolve_bulk_assigned_user(normalized.get('assigned_to'))
        if error:
            errors.append(error)
    elif kind == 'referrals':
        normalized['receiving_facility'], error = resolve_bulk_facility(normalized.get('receiving_facility'))
        if error:
            errors.append(error)
        normalized['assigned_mobiliser'], error = resolve_bulk_assigned_user(normalized.get('assigned_mobiliser'))
        if error:
            errors.append(error)
    elif kind == 'appointments':
        normalized['facility'], error = resolve_bulk_facility(normalized.get('facility'))
        if error:
            errors.append(error)
    return normalized, errors


def get_client_bulk_form(kind, data, client, user):
    spec = get_client_bulk_upload_spec(kind)
    if kind == 'appointments':
        return spec['form_class'](data, client=client, created_by=user)
    return spec['form_class'](data)


def save_client_bulk_form(kind, form, client, user):
    if kind == 'appointments':
        return form.save()

    obj = form.save(commit=False)
    obj.client = client
    if kind in {'journey-events', 'referrals'}:
        obj.recorded_by = user
    elif kind == 'follow-ups':
        obj.created_by = user
    obj.save()
    return obj


def validate_client_bulk_rows(kind, rows, client, user):
    spec = get_client_bulk_upload_spec(kind)
    results = []
    valid_rows = []
    for index, row in enumerate(rows, start=2):
        if not any((value or '').strip() for value in row.values()):
            continue
        normalized, errors = normalize_client_bulk_row(kind, row, spec['fields'])
        form = get_client_bulk_form(kind, normalized, client, user)
        if not form.is_valid():
            for field, field_errors in form.errors.items():
                label = field if field != '__all__' else 'row'
                errors.extend(f'{label}: {error}' for error in field_errors)
        valid = not errors
        results.append({
            'row_number': index,
            'valid': valid,
            'errors': errors,
            'data': normalized,
        })
        if valid:
            valid_rows.append(normalized)
    return results, valid_rows


def zamtel_sms_is_configured():
    return bool(settings.ZAMTEL_SMS_API_KEY and settings.ZAMTEL_SMS_URL)


def generate_account_otp():
    return get_random_string(6, allowed_chars='0123456789')


def send_zamtel_sms(phone_number, message):
    """Send an SMS through the configured Zamtel gateway."""
    if not zamtel_sms_is_configured():
        return False

    payload = json.dumps({
        'to': phone_number,
        'message': message,
        'sender': settings.ZAMTEL_SMS_SENDER_ID,
    }).encode('utf-8')
    request = Request(
        settings.ZAMTEL_SMS_URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {settings.ZAMTEL_SMS_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urlopen(request, timeout=settings.ZAMTEL_SMS_TIMEOUT_SECONDS) as response:
        return 200 <= response.status < 300


def issue_account_otp(user):
    otp = generate_account_otp()
    profile = user.profile
    profile.otp_code_hash = make_password(otp)
    profile.otp_expires_at = timezone.now() + ACCOUNT_OTP_TTL
    profile.save(update_fields=['otp_code_hash', 'otp_expires_at'])
    try:
        return send_zamtel_sms(
            profile.phone,
            f'Your MyThanzi verification code is {otp}. It expires in 10 minutes.',
        )
    except Exception:
        return False


def get_logged_in_user_ids():
    """Return user IDs referenced by unexpired authenticated sessions."""
    user_ids = set()
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        user_id = session.get_decoded().get('_auth_user_id')
        if user_id:
            user_ids.add(int(user_id))
    return set(User.objects.filter(pk__in=user_ids).values_list('pk', flat=True))


def logout_user_sessions(user):
    """Remove all active sessions for a user after credential reset."""
    deleted_count = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get('_auth_user_id') == str(user.pk):
            session.delete()
            deleted_count += 1
    return deleted_count


def ensure_session_key(request):
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key or ''
    if session_key:
        request.session['anonymous_submission_session_key'] = session_key
    return session_key


def get_submission_user(request):
    return request.user if request.user.is_authenticated else None


def serialize_form_answers(cleaned_data):
    answers = {}
    for key, value in cleaned_data.items():
        if isinstance(value, (date, datetime, time)):
            answers[key] = value.isoformat()
        elif hasattr(value, 'pk'):
            answers[key] = {
                'id': value.pk,
                'label': str(value),
            }
        else:
            answers[key] = value
    return answers


def claim_session_submissions_for_user(request, user):
    session_key = request.session.get('anonymous_submission_session_key') or request.session.session_key
    if not session_key:
        return

    submission_models = (
        SelfRiskAssessmentSubmission,
        SelfTestReportSubmission,
        SideEffectReportSubmission,
        ClinicFeedbackSubmission,
        SafeguardingCase,
        GrievanceCase,
        ClientExitInterview,
    )
    for model in submission_models:
        model.objects.filter(
            user__isnull=True,
            session_key=session_key,
        ).update(user=user)
    request.session.pop('anonymous_submission_session_key', None)


def get_user_management_stats():
    logged_in_user_ids = get_logged_in_user_ids()
    return {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'inactive': User.objects.filter(is_active=False).count(),
        'logged_in': len(logged_in_user_ids),
    }


def get_user_management_rows(search_term='', role_filter=''):
    users = User.objects.select_related(
        'profile__person_identity',
        'profile__facility__district',
        'profile__population_group',
    ).order_by('-date_joined')

    if search_term:
        users = users.filter(
            Q(username__icontains=search_term) |
            Q(first_name__icontains=search_term) |
            Q(last_name__icontains=search_term) |
            Q(email__icontains=search_term)
        )

    if role_filter:
        users = users.filter(profile__role=role_filter)

    logged_in_user_ids = get_logged_in_user_ids()
    users_with_profiles = []
    for user in users:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        users_with_profiles.append({
            'user': user,
            'profile': profile,
            'is_logged_in': user.pk in logged_in_user_ids,
        })

    return users_with_profiles


def population_group_matches_sex(population_group, sex):
    return (
        population_group
        and population_group.is_active
        and population_group.sex_eligibility in {'all', sex}
    )


def normalize_user_role_for_staff(role, is_staff):
    staff_roles = {value for value, _label in UserProfile.ROLE_CHOICES if value != 'client'}
    if is_staff:
        return role if role in staff_roles else ''
    return 'client'


def get_visible_appointments(user):
    queryset = Appointment.objects.select_related(
        'beneficiary__profile',
        'created_by__profile',
        'province',
        'district',
        'facility',
    )
    return queryset.filter(visible_appointment_filter(user))


def get_visible_clients(user):
    clients = User.objects.select_related(
        'profile__facility',
        'profile__person_identity',
    ).filter(
        profile__role='client',
        profile__is_active=True,
        is_active=True,
    )
    role = get_user_role(user)

    if user.is_superuser or role in USER_ADMIN_ROLES or role == 'supervisor':
        return clients

    if role in APPOINTMENT_ROLES:
        facility_id = getattr(getattr(user, 'profile', None), 'facility_id', None)
        if facility_id:
            return clients.filter(
                Q(profile__facility_id=facility_id) |
                Q(appointments__facility_id=facility_id) |
                Q(client_locator__service_point_id=facility_id)
            ).distinct()

        return clients.filter(
            Q(appointments__created_by=user) |
            Q(follow_up_tasks__assigned_to=user)
        ).distinct()

    return clients.filter(pk=user.pk)


def get_client_for_management(user, pk):
    return get_object_or_404(get_visible_clients(user), pk=pk)


def get_selected_person_identity(identity_id):
    if not identity_id:
        return None
    return PersonIdentity.objects.filter(pk=identity_id).first()


def ensure_user_person_identity(user):
    profile = user.profile
    if profile.person_identity_id:
        return profile.person_identity
    profile.person_identity = PersonIdentity.for_user_defaults(
        user,
        phone=profile.phone or '',
        date_of_birth=profile.date_of_birth,
    )
    profile.save(update_fields=['person_identity'])
    return profile.person_identity


def generate_temporary_password():
    return get_random_string(
        16,
        allowed_chars='abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*',
    )


def is_temporary_password_expired(user):
    profile = getattr(user, 'profile', None)
    expires_at = getattr(profile, 'temporary_password_expires_at', None)
    return bool(expires_at and expires_at <= timezone.now())


def get_user_for_expired_temporary_password(username, password):
    if not username or not password:
        return None

    try:
        user = User.objects.get_by_natural_key(username)
    except User.DoesNotExist:
        return None

    if user.check_password(password) and is_temporary_password_expired(user):
        return user

    return None


def login_view(request):
    """Authenticate a portal user and send them to an allowed landing page."""
    if request.user.is_authenticated:
        return redirect('portal_home')

    form = AuthenticationForm(request=request, data=request.POST or None)
    expired_temp_user = None
    if request.method == 'POST':
        expired_temp_user = get_user_for_expired_temporary_password(
            request.POST.get('username', ''),
            request.POST.get('password', ''),
        )

    if expired_temp_user:
        form.add_error(None, 'This temporary password has expired. Please request another password reset.')
    elif request.method == 'POST' and form.is_valid():
        user = form.get_user()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.is_active:
            form.add_error(None, 'This account has been disabled.')
        else:
            auth_login(request, user)
            claim_session_submissions_for_user(request, user)
            if profile.must_change_password:
                return redirect('password_change_required')
            next_url = request.POST.get('next', '')
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                if next_url == reverse('user_dashboard') and get_user_role(user) not in DASHBOARD_ROLES and not user.is_superuser:
                    return redirect(get_portal_landing_url(user))
                return redirect(next_url)
            return redirect('portal_home')

    return render(request, 'users/login.html', {
        'form': form,
        'next': request.POST.get('next') or request.GET.get('next', ''),
    })


def register_view(request):
    """Create a public client account and verify it with an SMS OTP when configured."""
    if request.user.is_authenticated:
        return redirect('portal_home')

    form = PublicRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        user.profile.role = 'client'
        user.profile.phone = form.cleaned_data['phone']
        user.profile.person_identity = PersonIdentity.for_user_defaults(
            user,
            phone=form.cleaned_data['phone'],
        )
        if zamtel_sms_is_configured():
            user.profile.is_active = False
            user.profile.is_phone_verified = False
            user.profile.save(update_fields=['role', 'phone', 'person_identity', 'is_active', 'is_phone_verified'])
            request.session['pending_verification_user_id'] = user.pk
            if issue_account_otp(user):
                messages.success(request, 'Your account has been created. Enter the OTP sent to your phone to activate it.')
            else:
                messages.error(request, 'Your account was created, but the OTP could not be sent. Please request a new code.')
            return redirect('verify_account')

        user.profile.is_active = True
        user.profile.is_phone_verified = True
        user.profile.otp_code_hash = ''
        user.profile.otp_expires_at = None
        user.profile.save(update_fields=[
            'role',
            'phone',
            'person_identity',
            'is_active',
            'is_phone_verified',
            'otp_code_hash',
            'otp_expires_at',
        ])
        auth_login(request, user)
        claim_session_submissions_for_user(request, user)
        messages.info(request, 'SMS verification is not configured, so OTP verification was skipped for this environment.')
        messages.success(request, 'Your account has been created successfully.')
        return redirect('portal_home')

    return render(request, 'users/register.html', {'form': form})


def verify_account_view(request):
    """Activate a newly registered account after OTP verification."""
    pending_user_id = request.session.get('pending_verification_user_id')
    if not pending_user_id:
        return redirect('register')

    user = get_object_or_404(User, pk=pending_user_id)
    profile = user.profile

    if not zamtel_sms_is_configured():
        profile.is_active = True
        profile.is_phone_verified = True
        profile.otp_code_hash = ''
        profile.otp_expires_at = None
        profile.save(update_fields=['is_active', 'is_phone_verified', 'otp_code_hash', 'otp_expires_at'])
        request.session.pop('pending_verification_user_id', None)
        auth_login(request, user)
        claim_session_submissions_for_user(request, user)
        messages.info(request, 'SMS verification is not configured, so OTP verification was skipped for this environment.')
        return redirect('portal_home')

    if request.method == 'POST':
        if 'resend' in request.POST:
            if issue_account_otp(user):
                messages.success(request, 'A new OTP has been sent.')
            else:
                messages.error(request, 'The OTP could not be sent. Please try again.')
            return redirect('verify_account')

        otp = request.POST.get('otp', '').strip()
        if not profile.otp_code_hash or not profile.otp_expires_at:
            messages.error(request, 'No active OTP was found. Request a new code.')
        elif profile.otp_expires_at <= timezone.now():
            messages.error(request, 'This OTP has expired. Request a new code.')
        elif not check_password(otp, profile.otp_code_hash):
            messages.error(request, 'Enter a valid OTP.')
        else:
            profile.is_active = True
            profile.is_phone_verified = True
            profile.otp_code_hash = ''
            profile.otp_expires_at = None
            profile.save(update_fields=['is_active', 'is_phone_verified', 'otp_code_hash', 'otp_expires_at'])
            request.session.pop('pending_verification_user_id', None)
            auth_login(request, user)
            claim_session_submissions_for_user(request, user)
            messages.success(request, 'Your account has been verified.')
            return redirect('portal_home')

    return render(request, 'users/verify_account.html', {
        'phone': profile.phone,
        'otp_expires_at': profile.otp_expires_at,
    })


@active_login_required
def password_change_required(request):
    """Require a flagged user to set a new password before using the portal."""
    profile = request.user.profile
    if not profile.must_change_password:
        return redirect('portal_home')

    form = SetPasswordForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        profile.must_change_password = False
        profile.temporary_password_expires_at = None
        profile.save(update_fields=['must_change_password', 'temporary_password_expires_at'])
        update_session_auth_hash(request, user)
        messages.success(request, 'Your password has been updated.')
        return redirect('portal_home')

    return render(request, 'users/password_change_required.html', {'form': form})


@require_POST
@login_required
def logout_view(request):
    request.user.profile.last_logout = timezone.now()
    request.user.profile.save(update_fields=['last_logout'])
    auth_logout(request)
    return redirect('login')


@require_POST
@login_required
def auto_logout_view(request):
    next_url = request.POST.get('next') or reverse('portal_home')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('portal_home')

    request.user.profile.last_logout = timezone.now()
    request.user.profile.save(update_fields=['last_logout'])
    auth_logout(request)

    login_url = f"{reverse('login')}?{urlencode({'next': next_url, 'idle_timeout': '1'})}"
    return JsonResponse({
        'success': True,
        'login_url': login_url,
    })


@never_cache
def session_status(request):
    """Let open portal tabs detect when their authenticated session is gone."""
    if request.user.is_authenticated:
        return JsonResponse({'authenticated': True})

    return JsonResponse({
        'authenticated': False,
        'login_url': f"{reverse('login')}?password_reset=1",
        'message': 'Your password has been reset. Please check your email for the temporary password. It is valid for 10 minutes.',
    }, status=401)


@require_POST
@active_login_required
def update_theme(request):
    theme_color = request.POST.get('theme_color')
    valid_themes = {choice[0] for choice in UserProfile.THEME_CHOICES}
    if theme_color in valid_themes:
        request.user.profile.theme_color = theme_color
        request.user.profile.save(update_fields=['theme_color'])

    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('portal_home')


@active_login_required
def portal_home(request):
    return redirect(get_portal_landing_url(request.user))


def get_portal_landing_url(user):
    role = get_user_role(user)
    if user.is_superuser or role in DASHBOARD_ROLES:
        return reverse('user_dashboard')
    if role in APPOINTMENT_ROLES:
        return reverse('client_management')
    return '/app/'


@active_login_required
def medication_reminders(request):
    for default in DEFAULT_NOTIFICATION_TYPE_SETTINGS:
        NotificationTypeSetting.objects.get_or_create(
            key=default['key'],
            defaults={
                'name': default['name'],
                'description': default['description'],
                'cadence': default['cadence'],
                'channel': default['channel'],
                'timing': default['timing'],
                'enabled': True,
                'is_system': True,
            },
        )

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'success': False, 'error': 'Invalid notification payload.'}, status=400)

        notification_types = payload.get('notification_types', [])
        if not isinstance(notification_types, list):
            return JsonResponse({'success': False, 'error': 'Notification types must be a list.'}, status=400)

        valid_channels = {choice[0] for choice in NotificationTypeSetting.CHANNEL_CHOICES}
        valid_cadences = {choice[0] for choice in NotificationTypeSetting.CADENCE_CHOICES}
        seen_keys = set()
        for item in notification_types:
            key = str(item.get('key', '')).strip().lower().replace(' ', '_')
            name = str(item.get('name', '')).strip()
            if not key or not name:
                return JsonResponse({'success': False, 'error': 'Every notification type needs a name and code.'}, status=400)
            if key in seen_keys:
                return JsonResponse({'success': False, 'error': f'Duplicate notification code: {key}.'}, status=400)
            seen_keys.add(key)
            channel = item.get('channel') if item.get('channel') in valid_channels else 'portal'
            cadence = item.get('cadence') if item.get('cadence') in valid_cadences else 'daily'
            NotificationTypeSetting.objects.update_or_create(
                key=key,
                defaults={
                    'name': name,
                    'description': str(item.get('description', '')).strip(),
                    'cadence': cadence,
                    'channel': channel,
                    'timing': str(item.get('timing', '')).strip() or '08:00',
                    'enabled': bool(item.get('enabled')),
                    'is_system': NotificationTypeSetting.objects.filter(key=key, is_system=True).exists(),
                },
            )

        NotificationTypeSetting.objects.exclude(key__in=seen_keys).delete()
        return JsonResponse({'success': True, 'count': len(seen_keys)})

    notification_types = [
        {
            'key': item.key,
            'name': item.name,
            'description': item.description,
            'cadence': item.cadence,
            'channel': item.channel,
            'timing': item.timing,
            'enabled': item.enabled,
        }
        for item in NotificationTypeSetting.objects.order_by('name')
    ]

    return render(request, 'users/medication_reminders.html', {
        'notification_types': notification_types,
    })


@active_login_required
def notification_inbox(request):
    notifications = Notification.objects.select_related(
        'appointment__facility',
        'appointment__district',
        'appointment__province',
        'actor',
    ).filter(
        recipient=request.user,
        channel='portal',
    )
    unread_count = notifications.filter(read_at__isnull=True).count()
    return render(request, 'users/notification_inbox.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@require_POST
@active_login_required
def notification_mark_read(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient=request.user,
        channel='portal',
    )
    notification.mark_read()
    next_url = request.POST.get('next') or reverse('notification_inbox')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('notification_inbox')


def calculate_self_risk_assessment(cleaned_data):
    score = 0
    risk_factors = []

    if cleaned_data.get('recent_test') in {'over_12_months', 'never'}:
        score += 2
        risk_factors.append('HIV testing may be overdue.')
    elif cleaned_data.get('recent_test') == '12_months':
        score += 1

    partner_scores = {'2_4': 2, '5_plus': 3}
    score += partner_scores.get(cleaned_data.get('partners'), 0)
    if cleaned_data.get('partners') in partner_scores:
        risk_factors.append('Multiple recent partners can increase exposure risk.')

    condom_scores = {'sometimes': 1, 'rarely': 2}
    score += condom_scores.get(cleaned_data.get('condom_use'), 0)
    if cleaned_data.get('condom_use') in condom_scores:
        risk_factors.append('Condom use has not been consistent.')

    if cleaned_data.get('partner_status') in {'yes', 'unsure'}:
        score += 2
        risk_factors.append('A partner has positive or unknown HIV status.')

    if cleaned_data.get('sti_symptoms') == 'yes':
        score += 2
        risk_factors.append('Recent STI symptoms or treatment can signal higher HIV exposure risk.')
    elif cleaned_data.get('sti_symptoms') == 'unsure':
        score += 1

    if cleaned_data.get('prep_use') in {'no', 'yes_past', 'unsure'}:
        score += 1

    if cleaned_data.get('pregnancy_or_breastfeeding') == 'yes':
        score += 1
        risk_factors.append('Pregnancy or breastfeeding is a good time to review HIV prevention options.')

    if cleaned_data.get('safety_concerns') == 'yes':
        score += 1
        risk_factors.append('Safety concerns may make prevention planning harder without support.')

    if score >= 7:
        level = 'Higher'
        badge = 'danger'
        summary = 'Your answers suggest higher HIV exposure risk. A provider can help with HIV testing, PrEP options, STI care, and a prevention plan that fits your situation.'
        next_steps = [
            'Book or visit a clinic for HIV testing and prevention counselling as soon as possible.',
            'Ask about PrEP options, including daily pills or long-acting injectable options where available.',
            'Seek urgent care if you may have been exposed to HIV within the last 72 hours.',
        ]
    elif score >= 4:
        level = 'Moderate'
        badge = 'warning'
        summary = 'Your answers show some risk factors. A clinic visit can help confirm your HIV status and choose the right prevention support.'
        next_steps = [
            'Schedule HIV testing if you have not tested recently.',
            'Discuss PrEP or other prevention methods with a health worker.',
            'Use condoms and consider STI screening if you have symptoms or a new partner.',
        ]
    else:
        level = 'Lower'
        badge = 'success'
        summary = 'Your answers suggest lower current HIV exposure risk. Keep testing regularly and continue prevention habits that work for you.'
        next_steps = [
            'Continue routine HIV testing based on your provider guidance.',
            'Use condoms and prevention medicine consistently when recommended.',
            'Retake this assessment if your relationship, partner status, or symptoms change.',
        ]

    return {
        'score': score,
        'level': level,
        'badge': badge,
        'summary': summary,
        'risk_factors': risk_factors,
        'next_steps': next_steps,
    }


def self_risk_assessment(request):
    result = None
    saved_submission = None
    form = SelfRiskAssessmentForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        result = calculate_self_risk_assessment(form.cleaned_data)
        saved_submission = SelfRiskAssessmentSubmission.objects.create(
            user=get_submission_user(request),
            session_key=ensure_session_key(request),
            answers=serialize_form_answers(form.cleaned_data),
            guidance=result,
            score=result['score'],
            level=result['level'],
        )

    return render(request, 'users/self_risk_assessment.html', {
        'form': form,
        'result': result,
        'saved_submission': saved_submission,
    })


def get_self_test_guidance(cleaned_data):
    result = cleaned_data.get('result')
    followed_instructions = cleaned_data.get('followed_instructions')
    confirmatory_test = cleaned_data.get('confirmatory_test')
    support_needed = cleaned_data.get('support_needed')

    if result == 'positive':
        level = 'Confirm at clinic'
        badge = 'danger'
        summary = 'A reactive self-test result must be confirmed by a trained health worker. The next step is confirmatory HIV testing and supportive counselling.'
        next_steps = [
            'Visit a clinic or contact a health worker for confirmatory testing as soon as possible.',
            'Do not start or stop HIV treatment based only on a self-test result.',
            'Bring the kit or a photo of the result if you can do so privately and safely.',
        ]
    elif result == 'negative':
        level = 'Negative reported'
        badge = 'success'
        summary = 'A negative self-test is reassuring, but recent exposure can still require repeat testing or prevention support.'
        next_steps = [
            'Repeat testing if you may have been exposed recently or if a provider recommends it.',
            'Consider PrEP, condoms, or other prevention options if you have ongoing exposure risk.',
            'Use the risk screening tool if you want help deciding what prevention support fits.',
        ]
    elif result == 'invalid':
        level = 'Retest needed'
        badge = 'warning'
        summary = 'An invalid or unclear result cannot confirm your HIV status. Use a new kit or visit a clinic for assisted testing.'
        next_steps = [
            'Use a new self-test kit and follow the timing instructions carefully.',
            'Visit a clinic if another result is unclear or if you need help reading it.',
            'Keep the used kit private and dispose of it safely.',
        ]
    else:
        level = 'Finish reading'
        badge = 'warning'
        summary = 'Read the test only within the kit instructions timing window. Reading too early or too late can make the result unreliable.'
        next_steps = [
            'Check the kit instructions for the correct reading time.',
            'If the reading window has passed, use a new kit or visit a clinic.',
            'Ask a health worker for support if you are unsure what the result means.',
        ]

    alerts = []
    if followed_instructions in {'no', 'unsure'}:
        alerts.append('The result may be less reliable if kit instructions or timing were not followed.')
    if result == 'positive' and confirmatory_test != 'yes':
        alerts.append('Confirmatory testing is still needed before any diagnosis or treatment decision.')
    if support_needed == 'yes':
        alerts.append('A health worker can help with confirmatory testing, counselling, prevention, or linkage to care.')

    return {
        'level': level,
        'badge': badge,
        'summary': summary,
        'next_steps': next_steps,
        'alerts': alerts,
    }


def self_test_report(request):
    guidance = None
    saved_submission = None
    form = SelfTestReportForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_self_test_guidance(form.cleaned_data)
        saved_submission = SelfTestReportSubmission.objects.create(
            user=get_submission_user(request),
            session_key=ensure_session_key(request),
            answers=serialize_form_answers(form.cleaned_data),
            guidance=guidance,
            test_date=form.cleaned_data['test_date'],
            result=form.cleaned_data['result'],
        )

    return render(request, 'users/self_test_report.html', {
        'form': form,
        'guidance': guidance,
        'saved_submission': saved_submission,
    })


def get_side_effect_guidance(cleaned_data):
    severity = cleaned_data.get('severity')
    urgent_symptoms = cleaned_data.get('urgent_symptoms')
    status = cleaned_data.get('status')
    stopped_medicine = cleaned_data.get('stopped_medicine')
    facility_visit = cleaned_data.get('facility_visit')
    support_needed = cleaned_data.get('support_needed')

    if urgent_symptoms == 'yes' or severity == 'severe':
        level = 'Urgent care'
        badge = 'danger'
        summary = 'Your report includes symptoms that need urgent clinical attention. Please contact emergency services, a clinic, or a health worker now.'
        next_steps = [
            'Seek urgent care now, especially for breathing problems, chest pain, fainting, swelling, or severe rash.',
            'Bring your medication package, injection card, or product name if you can.',
            'Do not take another dose until a health worker advises you if symptoms are severe.',
        ]
    elif severity == 'moderate' or status == 'worse':
        level = 'Clinical follow-up'
        badge = 'warning'
        summary = 'Your symptoms may need review by a provider, especially if they are affecting daily activities or getting worse.'
        next_steps = [
            'Contact a clinic or health worker for assessment and side-effect management.',
            'Keep a note of when symptoms started, how often they happen, and any missed doses.',
            'Ask whether you should continue, pause, or switch prevention options.',
        ]
    else:
        level = 'Monitor symptoms'
        badge = 'success'
        summary = 'Your report sounds mild or improving. Continue monitoring and seek care if symptoms worsen or do not settle.'
        next_steps = [
            'Track symptoms for the next few days and keep using the medicine as advised.',
            'Contact a clinic if the side effect gets worse, persists, or worries you.',
            'Report any new severe symptoms immediately.',
        ]

    alerts = []
    if stopped_medicine == 'yes':
        alerts.append('Tell a provider you stopped or missed medicine so they can help keep your prevention plan effective.')
    if facility_visit != 'yes':
        alerts.append('A health worker can confirm whether the symptom is medicine-related and advise what to do next.')
    if support_needed == 'yes':
        alerts.append('Follow-up support is recommended based on your preference.')

    return {
        'level': level,
        'badge': badge,
        'summary': summary,
        'next_steps': next_steps,
        'alerts': alerts,
    }


def side_effect_report(request):
    guidance = None
    saved_submission = None
    form = SideEffectReportForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_side_effect_guidance(form.cleaned_data)
        saved_submission = SideEffectReportSubmission.objects.create(
            user=get_submission_user(request),
            session_key=ensure_session_key(request),
            answers=serialize_form_answers(form.cleaned_data),
            guidance=guidance,
            symptom_start_date=form.cleaned_data['symptom_start_date'],
            severity=form.cleaned_data['severity'],
            follow_up_requested=form.cleaned_data.get('support_needed') == 'yes',
        )

    return render(request, 'users/side_effect_report.html', {
        'form': form,
        'guidance': guidance,
        'saved_submission': saved_submission,
    })


def get_clinic_feedback_guidance(cleaned_data):
    overall_rating = int(cleaned_data.get('overall_rating') or 0)
    wait_time_rating = int(cleaned_data.get('wait_time_rating') or 0)
    staff_respect_rating = int(cleaned_data.get('staff_respect_rating') or 0)
    medicine_availability = cleaned_data.get('medicine_availability')
    would_recommend = cleaned_data.get('would_recommend')
    follow_up_needed = cleaned_data.get('follow_up_needed')

    average_rating = round((overall_rating + wait_time_rating + staff_respect_rating) / 3, 1)

    if average_rating <= 2.5 or medicine_availability == 'no' or would_recommend == 'no':
        level = 'Needs review'
        badge = 'warning'
        summary = 'Thank you for reporting a clinic experience that may need follow-up. Your feedback highlights service areas that should be reviewed.'
        next_steps = [
            'A supervisor or health worker should review the service concern if follow-up is requested.',
            'Use Find a Clinic if you need another nearby service point.',
            'Seek urgent care immediately if the clinic visit was related to a serious health concern.',
        ]
    elif average_rating < 4:
        level = 'Feedback received'
        badge = 'success'
        summary = 'Thank you. Your feedback notes a mixed service experience and can help improve clinic quality.'
        next_steps = [
            'Your rating can help identify service improvements.',
            'Share specific comments when possible so teams know what to improve.',
            'Return for scheduled follow-up or use Find a Clinic for alternatives.',
        ]
    else:
        level = 'Positive rating'
        badge = 'success'
        summary = 'Thank you for sharing a positive clinic experience. Feedback like this helps identify what is working well.'
        next_steps = [
            'Keep attending scheduled visits and prevention follow-ups.',
            'Share any specific staff or service strengths in the comments next time.',
            'Retake this form after future visits if your experience changes.',
        ]

    alerts = []
    if wait_time_rating <= 2:
        alerts.append('Waiting time was rated low and may need attention.')
    if staff_respect_rating <= 2:
        alerts.append('Respect or privacy was rated low and should be reviewed.')
    if follow_up_needed == 'yes':
        alerts.append('Follow-up was requested for this feedback.')

    return {
        'level': level,
        'badge': badge,
        'summary': summary,
        'next_steps': next_steps,
        'alerts': alerts,
        'average_rating': average_rating,
    }


def clinic_feedback(request):
    guidance = None
    saved_submission = None
    form = ClinicFeedbackForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_clinic_feedback_guidance(form.cleaned_data)
        saved_submission = ClinicFeedbackSubmission.objects.create(
            user=get_submission_user(request),
            session_key=ensure_session_key(request),
            answers=serialize_form_answers(form.cleaned_data),
            guidance=guidance,
            facility=form.cleaned_data['facility'],
            visit_date=form.cleaned_data['visit_date'],
            average_rating=guidance['average_rating'],
            follow_up_requested=form.cleaned_data.get('follow_up_needed') == 'yes',
        )

    return render(request, 'users/clinic_feedback.html', {
        'form': form,
        'guidance': guidance,
        'saved_submission': saved_submission,
    })


@active_login_required
def safeguarding_report(request):
    cases = SafeguardingCase.objects.select_related('location_facility__district__province').filter(user=request.user).order_by('-submitted_at')
    form = SafeguardingReportForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        is_draft = action == 'draft'
        case_id = request.POST.get('case_id')
        instance = None
        if case_id:
            instance = get_object_or_404(SafeguardingCase, pk=case_id, user=request.user)
            if instance.status != 'draft' and is_draft:
                messages.error(request, 'Submitted safeguarding cases cannot be moved back to draft.')
                return redirect('safeguarding_report')

        form = SafeguardingReportForm(request.POST, instance=instance, is_draft=is_draft)
        if form.is_valid():
            saved_case = form.save(commit=False)
            saved_case.user = request.user
            saved_case.session_key = ensure_session_key(request)
            saved_case.answers = serialize_form_answers(form.cleaned_data)
            if is_draft:
                saved_case.status = 'draft'
                saved_case.guidance = {
                    'summary': 'Draft saved.',
                    'next_steps': ['Return to this safeguarding case when you are ready to submit it.'],
                }
                message = 'Safeguarding draft saved.'
            else:
                saved_case.status = 'received'
                saved_case.guidance = {
                    'summary': 'Your safeguarding report has been received.',
                    'next_steps': [
                        'Keep the reference number for follow-up.',
                        'A safeguarding focal point will review the report.',
                    ],
                }
                message = 'Safeguarding case submitted.'
            saved_case.risk_trigger_flag = form.cleaned_data.get('severity') in {'high', 'critical'}
            saved_case.save()
            messages.success(request, message)
            return redirect('safeguarding_report')
        messages.error(request, 'Please check the safeguarding case details.')

    return render(request, 'users/safeguarding_report.html', {
        'form': form,
        'cases': cases,
    })


@role_required(*USER_ADMIN_ROLES)
def safeguarding_management(request):
    status_filter = request.GET.get('status', '').strip()
    cases = SafeguardingCase.objects.select_related('user', 'focal_point', 'location_facility').exclude(status='draft')
    if status_filter:
        cases = cases.filter(status=status_filter)

    today = timezone.localdate()
    stats = {
        'total': SafeguardingCase.objects.exclude(status='draft').count(),
        'open': SafeguardingCase.objects.exclude(status__in=['draft', 'resolved', 'closed']).count(),
        'overdue': SafeguardingCase.objects.exclude(status__in=['draft', 'resolved', 'closed']).filter(sla_deadline__lt=today).count(),
        'cab_ready': SafeguardingCase.objects.exclude(status='draft').filter(cab_oversight_ready=True).count(),
    }
    return render(request, 'users/case_management.html', {
        'title': 'Safeguarding Cases',
        'subtitle': 'Track anonymous reports, focal point escalation, confidentiality, SLA status, and CAB oversight.',
        'icon': 'shield',
        'records': cases.order_by('status', 'sla_deadline', '-submitted_at'),
        'stats': stats,
        'status_choices': SafeguardingCase.STATUS_CHOICES,
        'status_filter': status_filter,
        'detail_url_name': 'safeguarding_case_detail',
        'reference_label': 'Case',
        'empty_message': 'No safeguarding cases found.',
    })


@role_required(*USER_ADMIN_ROLES)
def safeguarding_case_detail(request, pk):
    case = get_object_or_404(SafeguardingCase.objects.select_related('user', 'focal_point', 'location_facility'), pk=pk)
    form = SafeguardingCaseUpdateForm(request.POST or None, instance=case)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Safeguarding case updated.')
        return redirect('safeguarding_case_detail', pk=case.pk)

    return render(request, 'users/case_detail.html', {
        'title': case.reference_number,
        'back_url_name': 'safeguarding_management',
        'record': case,
        'form': form,
        'sensitive_body': case.incident_details,
        'detail_rows': [
            ('Incident type', case.get_incident_type_display()),
            ('Incident date', case.incident_date or 'Not provided'),
            ('Location / Facility', case.location_facility or case.location or 'Not provided'),
            ('Severity', case.get_severity_display()),
            ('Status', case.get_status_display()),
            ('SLA deadline', case.sla_deadline),
            ('Focal point', case.focal_point or 'Not assigned'),
            ('Risk trigger', 'Yes' if case.risk_trigger_flag else 'No'),
        ],
    })


def grievance_submit(request):
    saved_case = None
    form = GrievanceSubmissionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        saved_case = form.save(commit=False)
        saved_case.user = get_submission_user(request)
        saved_case.session_key = ensure_session_key(request)
        saved_case.answers = serialize_form_answers(form.cleaned_data)
        saved_case.guidance = {
            'summary': 'Your grievance has been received.',
            'next_steps': [
                'Keep the reference number for follow-up.',
                'The responsible team will review and respond where contact is available.',
            ],
        }
        saved_case.save()
        form = GrievanceSubmissionForm()

    return render(request, 'users/module_submission_form.html', {
        'title': 'Submit a Grievance',
        'subtitle': 'Submit a programme complaint through the grievance mechanism.',
        'icon': 'campaign',
        'form': form,
        'saved_record': saved_case,
        'reference_label': 'Grievance reference',
    })


@role_required(*USER_ADMIN_ROLES)
def grievance_management(request):
    status_filter = request.GET.get('status', '').strip()
    cases = GrievanceCase.objects.select_related('user', 'assigned_to', 'district__province')
    if status_filter:
        cases = cases.filter(status=status_filter)

    today = timezone.localdate()
    stats = {
        'total': GrievanceCase.objects.count(),
        'open': GrievanceCase.objects.exclude(status__in=['resolved', 'closed']).count(),
        'overdue': GrievanceCase.objects.exclude(status__in=['resolved', 'closed']).filter(sla_deadline__lt=today).count(),
        'urgent': GrievanceCase.objects.filter(priority='urgent').count(),
    }
    district_summary = (
        GrievanceCase.objects
        .values('district__name')
        .annotate(total=Count('pk'))
        .order_by('-total')[:8]
    )
    category_summary = (
        GrievanceCase.objects
        .values('category')
        .annotate(total=Count('pk'))
        .order_by('-total')
    )
    return render(request, 'users/case_management.html', {
        'title': 'Grievance Cases',
        'subtitle': 'Track complaints, priority, investigator assignment, escalation, response, SLA, and district analytics.',
        'icon': 'campaign',
        'records': cases.order_by('status', 'sla_deadline', '-submitted_at'),
        'stats': stats,
        'status_choices': GrievanceCase.STATUS_CHOICES,
        'status_filter': status_filter,
        'detail_url_name': 'grievance_case_detail',
        'reference_label': 'Grievance',
        'empty_message': 'No grievance cases found.',
        'district_summary': district_summary,
        'category_summary': category_summary,
    })


@role_required(*USER_ADMIN_ROLES)
def grievance_case_detail(request, pk):
    case = get_object_or_404(GrievanceCase.objects.select_related('user', 'assigned_to', 'district__province'), pk=pk)
    form = GrievanceCaseUpdateForm(request.POST or None, instance=case)
    if request.method == 'POST' and form.is_valid():
        updated_case = form.save(commit=False)
        if updated_case.escalation_target and updated_case.status not in {'resolved', 'closed'}:
            updated_case.status = 'escalated'
        updated_case.save()
        messages.success(request, 'Grievance case updated.')
        return redirect('grievance_case_detail', pk=case.pk)

    return render(request, 'users/case_detail.html', {
        'title': case.reference_number,
        'back_url_name': 'grievance_management',
        'record': case,
        'form': form,
        'sensitive_body': case.complaint_details,
        'detail_rows': [
            ('Channel', case.get_submission_channel_display()),
            ('Category', case.get_category_display()),
            ('Priority', case.get_priority_display()),
            ('Status', case.get_status_display()),
            ('District', case.district or 'Not provided'),
            ('SLA deadline', case.sla_deadline),
            ('Assigned to', case.assigned_to or 'Not assigned'),
            ('Response provided', 'Yes' if case.response_provided else 'No'),
            ('Escalation', case.get_escalation_target_display() if case.escalation_target else 'Not escalated'),
        ],
    })


def client_exit_interview(request):
    saved_interview = None
    form = ClientExitInterviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        saved_interview = form.save(commit=False)
        saved_interview.user = get_submission_user(request)
        saved_interview.session_key = ensure_session_key(request)
        saved_interview.answers = serialize_form_answers(form.cleaned_data)
        saved_interview.guidance = {
            'summary': 'Your exit interview has been received.',
            'next_steps': ['Responses are aggregated into quality dashboards.'],
        }
        saved_interview.save()
        form = ClientExitInterviewForm()

    return render(request, 'users/module_submission_form.html', {
        'title': 'Client Exit Interview',
        'subtitle': 'Share service experience without exposing names or biometric data.',
        'icon': 'rate_review',
        'form': form,
        'saved_record': saved_interview,
        'reference_label': 'Submission',
    })


@role_required(*USER_ADMIN_ROLES)
def exit_interview_dashboard(request):
    interviews = ClientExitInterview.objects.select_related(
        'service_point__district__province',
        'population_group',
        'user',
    )
    stats = {
        'total': interviews.count(),
        'avg_waiting': interviews.aggregate(value=Avg('waiting_time_rating'))['value'] or 0,
        'avg_staff': interviews.aggregate(value=Avg('staff_attitude_rating'))['value'] or 0,
        'avg_clarity': interviews.aggregate(value=Avg('information_clarity_score'))['value'] or 0,
    }
    return render(request, 'users/exit_interview_dashboard.html', {
        'interviews': interviews.order_by('-submitted_at'),
        'stats': stats,
        'population_summary': interviews.values('population_group__name').annotate(total=Count('pk')).order_by('-total'),
        'service_point_summary': interviews.values('service_point__name').annotate(total=Count('pk')).order_by('-total')[:10],
    })


@role_required(*USER_ADMIN_ROLES)
def user_list(request):
    """Display users management list with edit/delete options"""
    search_term = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    users_with_profiles = get_user_management_rows(search_term, role_filter)
    
    context = {
        'users': users_with_profiles,
        'search_term': search_term,
        'role_filter': role_filter,
        'role_choices': UserProfile.ROLE_CHOICES,
        'sex_choices': UserProfile.SEX_CHOICES,
        'person_identity_choices': PersonIdentity.objects.order_by('full_name', 'id'),
        'facility_choices': Facility.objects.select_related('district__province').order_by(
            'district__province__name',
            'district__name',
            'name',
        ),
        'population_group_choices': PopulationGroup.objects.filter(is_active=True).order_by('name'),
        'facility_options': [
            {
                'id': facility.pk,
                'label': f'{facility.name} - {facility.district.name}, {facility.district.province.name}',
            }
            for facility in Facility.objects.select_related('district__province').order_by(
                'district__province__name',
                'district__name',
                'name',
            )
        ],
    }
    return render(request, 'users/user_management.html', context)


@role_required(*USER_ADMIN_ROLES)
def population_group_management(request):
    """Create and manage client population groups."""
    form = PopulationGroupForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Population group saved.')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('population_group_management')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    search_term = request.GET.get('q', '').strip()
    groups = PopulationGroup.objects.annotate(client_count=Count('client_profiles'))
    if search_term:
        groups = groups.filter(
            Q(name__icontains=search_term) |
            Q(code__icontains=search_term) |
            Q(description__icontains=search_term)
        )

    return render(request, 'users/population_group_management.html', {
        'form': form,
        'groups': groups.order_by('name'),
        'search_term': search_term,
    })


@role_required(*USER_ADMIN_ROLES)
def population_group_edit(request, pk):
    group = get_object_or_404(PopulationGroup, pk=pk)
    form = PopulationGroupForm(request.POST or None, instance=group)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Population group updated.')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('population_group_management')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    return render(request, 'users/population_group_form.html', {
        'form': form,
        'group': group,
        'title': f'Edit {group.name}',
    })


@require_POST
@role_required(*USER_ADMIN_ROLES)
def population_group_delete(request, pk):
    group = get_object_or_404(PopulationGroup, pk=pk)
    try:
        group.delete()
        messages.success(request, 'Population group deleted.')
    except ProtectedError:
        messages.error(request, 'This population group is assigned to clients and cannot be deleted.')
    return redirect('population_group_management')


@role_required(*APPOINTMENT_ROLES)
def client_management(request):
    """Client management workspace for locator, journey, referral, and follow-up workflows."""
    search_term = request.GET.get('q', '').strip()
    clients = get_visible_clients(request.user)

    if search_term:
        clients = clients.filter(
            Q(username__icontains=search_term) |
            Q(first_name__icontains=search_term) |
            Q(last_name__icontains=search_term) |
            Q(email__icontains=search_term) |
            Q(profile__reference_number__icontains=search_term) |
            Q(profile__phone__icontains=search_term) |
            Q(client_locator__mobiliser_zone__icontains=search_term)
        )

    client_rows = []
    for client in clients.order_by('first_name', 'last_name', 'username'):
        client_rows.append({
            'client': client,
            'latest_journey': client.journey_events.first(),
            'open_tasks': client.follow_up_tasks.exclude(status__in=['completed', 'cancelled']).count(),
            'referrals': client.referral_records.count(),
        })

    return render(request, 'users/client_management.html', {
        'client_rows': client_rows,
        'search_term': search_term,
    })


@role_required(*APPOINTMENT_ROLES)
def client_record(request, pk):
    """Single client record for non-identifying profile, locator, journey, referral, and consent controls."""
    client = get_client_for_management(request.user, pk)
    locator, _ = ClientLocator.objects.get_or_create(client=client)
    consent, _ = ClientConsent.objects.get_or_create(client=client)

    locator_form = ClientLocatorForm(instance=locator, prefix='locator')
    journey_formset = ClientJourneyEventFormSet(prefix='journey')
    referral_form = ReferralRecordForm(prefix='referral')
    follow_up_form = FollowUpTaskForm(prefix='followup')
    consent_form = ClientConsentForm(instance=consent, prefix='consent')
    appointment_form = ClientAppointmentForm(prefix='appointment', client=client, created_by=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'locator':
            locator_form = ClientLocatorForm(request.POST, instance=locator, prefix='locator')
            if locator_form.is_valid():
                locator = locator_form.save(commit=False)
                locator.client = client
                locator.updated_by = request.user
                locator.save()
                messages.success(request, 'Client locator details saved.')
                return redirect('client_record', pk=client.pk)
        elif action == 'journey':
            journey_formset = ClientJourneyEventFormSet(request.POST, prefix='journey')
            if journey_formset.is_valid():
                created_events = 0
                for journey_form in journey_formset:
                    if not journey_form.has_changed():
                        continue
                    event = journey_form.save(commit=False)
                    event.client = client
                    event.recorded_by = request.user
                    event.save()
                    created_events += 1
                if created_events:
                    messages.success(request, f'{created_events} journey event{"s" if created_events != 1 else ""} recorded.')
                else:
                    messages.warning(request, 'Add at least one journey event before saving.')
                return redirect('client_record', pk=client.pk)
        elif action == 'referral':
            referral_form = ReferralRecordForm(request.POST, prefix='referral')
            if referral_form.is_valid():
                referral = referral_form.save(commit=False)
                referral.client = client
                referral.recorded_by = request.user
                referral.save()
                messages.success(request, 'Referral record saved.')
                return redirect('client_record', pk=client.pk)
        elif action == 'followup':
            follow_up_form = FollowUpTaskForm(request.POST, prefix='followup')
            if follow_up_form.is_valid():
                task = follow_up_form.save(commit=False)
                task.client = client
                task.created_by = request.user
                task.save()
                messages.success(request, 'Follow-up task saved.')
                return redirect('client_record', pk=client.pk)
        elif action == 'appointment':
            appointment_form = ClientAppointmentForm(
                request.POST,
                prefix='appointment',
                client=client,
                created_by=request.user,
            )
            if appointment_form.is_valid():
                appointment = appointment_form.save()
                portal_notification, email_notification = notify_appointment_created(appointment, actor=request.user)
                messages.success(request, 'Appointment booked.')
                if email_notification and email_notification.status == 'failed':
                    messages.warning(request, 'The portal notification was created, but the email notification could not be sent.')
                elif portal_notification and not appointment.beneficiary.email:
                    messages.warning(request, 'The portal notification was created. No email was sent because the client has no email address.')
                return redirect('client_record', pk=client.pk)
        elif action == 'consent':
            consent_form = ClientConsentForm(request.POST, instance=consent, prefix='consent')
            if consent_form.is_valid():
                consent = consent_form.save(commit=False)
                consent.client = client
                consent.recorded_by = request.user
                consent.save()
                messages.success(request, 'Consent and privacy controls saved.')
                return redirect('client_record', pk=client.pk)

    return render(request, 'users/client_record.html', {
        'client': client,
        'locator': locator,
        'consent': consent,
        'locator_form': locator_form,
        'journey_formset': journey_formset,
        'referral_form': referral_form,
        'follow_up_form': follow_up_form,
        'consent_form': consent_form,
        'appointment_form': appointment_form,
        'journey_events': client.journey_events.all()[:10],
        'referrals': client.referral_records.all()[:10],
        'follow_up_tasks': client.follow_up_tasks.all()[:10],
        'appointments': get_visible_appointments(request.user).filter(beneficiary=client)[:10],
    })


def build_referral_qr_data_uri(value):
    try:
        import qrcode
    except ImportError:
        return ''

    image = qrcode.make(value)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


@role_required(*APPOINTMENT_ROLES)
def referral_slip(request, referral_code):
    referral = get_object_or_404(
        ReferralRecord.objects.select_related(
            'receiving_facility',
            'receiving_facility__district',
            'client',
            'recorded_by',
        ),
        referral_code=referral_code,
    )
    record_url = request.build_absolute_uri(reverse('referral_scan', kwargs={'referral_code': referral.referral_code}))
    return render(request, 'users/referral_slip.html', {
        'referral': referral,
        'record_url': record_url,
        'qr_data_uri': build_referral_qr_data_uri(record_url),
    })


def referral_scan_denied_response():
    return HttpResponse(get_random_string(96), content_type='text/plain; charset=utf-8')


def can_open_referral_scan(user, referral):
    if not user.is_authenticated:
        return False
    profile = getattr(user, 'profile', None)
    if not profile or not profile.is_active:
        return False
    if profile.must_change_password:
        return False
    if profile.role not in {'provider', 'chw', 'mobiliser', 'supervisor'}:
        return False
    if not referral.receiving_facility_id:
        return False
    return profile.facility_id == referral.receiving_facility_id


def referral_scan(request, referral_code):
    referral = ReferralRecord.objects.select_related(
        'assigned_mobiliser',
        'client',
        'client__profile',
        'confirmed_by',
        'receiving_facility',
        'receiving_facility__district',
        'recorded_by',
    ).filter(referral_code=referral_code).first()
    if not referral or not can_open_referral_scan(request.user, referral):
        return referral_scan_denied_response()

    follow_up_tasks = referral.client.follow_up_tasks.filter(
        reason='referral_confirmation',
        notes__icontains=referral.referral_code,
    ).select_related('assigned_to')[:5]
    return render(request, 'users/referral_detail.html', {
        'referral': referral,
        'follow_up_tasks': follow_up_tasks,
        'scanned_referral': True,
    })


@role_required(*APPOINTMENT_ROLES)
def referral_detail(request, referral_code):
    referral = get_object_or_404(
        ReferralRecord.objects.select_related(
            'assigned_mobiliser',
            'client',
            'client__profile',
            'confirmed_by',
            'receiving_facility',
            'receiving_facility__district',
            'recorded_by',
        ),
        referral_code=referral_code,
    )
    follow_up_tasks = referral.client.follow_up_tasks.filter(
        reason='referral_confirmation',
        notes__icontains=referral.referral_code,
    ).select_related('assigned_to')[:5]
    return render(request, 'users/referral_detail.html', {
        'referral': referral,
        'follow_up_tasks': follow_up_tasks,
    })


@role_required(*APPOINTMENT_ROLES)
def referral_confirm(request, referral_code):
    referral = get_object_or_404(
        ReferralRecord.objects.select_related('client', 'receiving_facility'),
        referral_code=referral_code,
    )
    form = ReferralConfirmationForm(instance=referral)
    if request.method == 'POST':
        form = ReferralConfirmationForm(request.POST, instance=referral)
        if form.is_valid():
            confirmed_referral = form.save(commit=False)
            confirmed_referral.confirmed_by = request.user
            confirmed_referral.save()
            messages.success(request, 'Referral confirmation saved.')
            return redirect('referral_detail', referral_code=confirmed_referral.referral_code)
    return render(request, 'users/referral_confirm.html', {
        'referral': referral,
        'form': form,
    })


def referral_rate(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, 1)


@role_required(*DASHBOARD_ROLES)
def referral_analytics(request):
    referrals = ReferralRecord.objects.select_related(
        'receiving_facility__district',
        'assigned_mobiliser',
        'client__profile__population_group',
    )
    total = referrals.count()
    completed = referrals.filter(confirmation_status__in=ReferralRecord.COMPLETED_STATUSES).count()
    converted = referrals.filter(initiation_outcome__in=['len_prep_initiated', 'hivst_received']).count()
    not_attended = referrals.filter(confirmation_status='not_attended').count()

    by_status = referrals.values('confirmation_status').annotate(total=Count('id')).order_by('-total')
    by_district = referrals.values(
        'receiving_facility__district__name',
    ).annotate(total=Count('id')).order_by('-total', 'receiving_facility__district__name')
    by_zone = referrals.values(
        'client__client_locator__mobiliser_zone',
    ).annotate(total=Count('id')).order_by('-total', 'client__client_locator__mobiliser_zone')
    by_kpp = referrals.values(
        'client__profile__population_group__name',
    ).annotate(total=Count('id')).order_by('-total', 'client__profile__population_group__name')
    by_mobiliser = referrals.values(
        'assigned_mobiliser__first_name',
        'assigned_mobiliser__last_name',
        'assigned_mobiliser__username',
    ).annotate(total=Count('id')).order_by('-total', 'assigned_mobiliser__username')

    return render(request, 'users/referral_analytics.html', {
        'total_referrals': total,
        'completed_referrals': completed,
        'converted_referrals': converted,
        'not_attended_referrals': not_attended,
        'completion_rate': referral_rate(completed, total),
        'conversion_rate': referral_rate(converted, total),
        'drop_off_rate': referral_rate(not_attended, total),
        'by_status': by_status,
        'by_district': by_district,
        'by_zone': by_zone,
        'by_kpp': by_kpp,
        'by_mobiliser': by_mobiliser,
    })


@role_required(*APPOINTMENT_ROLES)
def client_bulk_upload_template(request, pk, kind):
    """Download a CSV template for client record bulk creation."""
    client = get_client_for_management(request.user, pk)
    spec = get_client_bulk_upload_spec(kind)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{spec["filename"]}"'
    writer = csv.DictWriter(response, fieldnames=spec['fields'])
    writer.writeheader()
    writer.writerows(get_client_bulk_template_rows(kind))
    return response


@role_required(*APPOINTMENT_ROLES)
def client_bulk_upload_validate(request, pk, kind):
    """Validate a CSV upload before committing client record objects."""
    client = get_client_for_management(request.user, pk)
    spec = get_client_bulk_upload_spec(kind)
    session_key = get_client_bulk_session_key(client, kind)
    results = []
    commit_ready = False
    uploaded_filename = ''

    if request.method == 'POST':
        upload = request.FILES.get('bulk_file')
        if not upload:
            messages.error(request, 'Choose a CSV file to validate.')
        else:
            uploaded_filename = upload.name
            try:
                csv_text = upload.read().decode('utf-8-sig')
                reader = csv.DictReader(io.StringIO(csv_text))
                missing_fields = [field for field in spec['fields'] if field not in (reader.fieldnames or [])]
                if missing_fields:
                    messages.error(request, f'Missing required column{"s" if len(missing_fields) != 1 else ""}: {", ".join(missing_fields)}.')
                    request.session.pop(session_key, None)
                else:
                    rows = list(reader)
                    results, valid_rows = validate_client_bulk_rows(kind, rows, client, request.user)
                    if not results:
                        messages.error(request, 'The CSV file has no rows to upload.')
                        request.session.pop(session_key, None)
                    elif all(result['valid'] for result in results):
                        request.session[session_key] = valid_rows
                        request.session.modified = True
                        commit_ready = True
                        messages.success(request, 'Validation passed. Review the rows, then submit to post them.')
                    else:
                        request.session.pop(session_key, None)
                        messages.error(request, 'Validation failed. Fix the rows marked with errors and upload again.')
            except UnicodeDecodeError:
                request.session.pop(session_key, None)
                messages.error(request, 'Upload a UTF-8 encoded CSV file.')
            except csv.Error as exc:
                request.session.pop(session_key, None)
                messages.error(request, f'The CSV file could not be read: {exc}')

    return render(request, 'users/client_bulk_upload.html', {
        'client': client,
        'kind': kind,
        'spec': spec,
        'results': results,
        'commit_ready': commit_ready,
        'uploaded_filename': uploaded_filename,
    })


@role_required(*APPOINTMENT_ROLES)
@require_POST
def client_bulk_upload_commit(request, pk, kind):
    """Create client record objects from the previously validated bulk upload."""
    client = get_client_for_management(request.user, pk)
    spec = get_client_bulk_upload_spec(kind)
    session_key = get_client_bulk_session_key(client, kind)
    rows = request.session.get(session_key)
    if not rows:
        messages.error(request, 'Validate a CSV file before submitting the upload.')
        return redirect('client_bulk_upload', pk=client.pk, kind=kind)

    results, valid_rows = validate_client_bulk_rows(kind, rows, client, request.user)
    if not results or len(valid_rows) != len(results):
        request.session.pop(session_key, None)
        messages.error(request, 'The validated upload is no longer valid. Please upload and validate the file again.')
        return redirect('client_bulk_upload', pk=client.pk, kind=kind)

    with transaction.atomic():
        for row in valid_rows:
            form = get_client_bulk_form(kind, row, client, request.user)
            if not form.is_valid():
                raise ValueError(f'Validated {spec["label"]} row failed during save.')
            save_client_bulk_form(kind, form, client, request.user)

    request.session.pop(session_key, None)
    messages.success(request, f'{len(valid_rows)} {spec["label"].lower()} row{"s" if len(valid_rows) != 1 else ""} posted.')
    return redirect('client_record', pk=client.pk)


@active_login_required
def my_journey(request):
    """Show the signed-in user's own care journey timeline."""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    locator = getattr(user, 'client_locator', None)
    consent = getattr(user, 'client_consent', None)
    appointments = Appointment.objects.filter(beneficiary=user).select_related('facility', 'district', 'province')
    journey_events = user.journey_events.select_related('recorded_by').all()
    referrals = user.referral_records.select_related('recorded_by', 'receiving_facility').all()
    follow_up_tasks = user.follow_up_tasks.select_related('assigned_to').all()

    timeline = []
    for event in journey_events:
        timeline.append({
            'date': event.event_date,
            'type': 'Journey',
            'title': event.get_stage_display(),
            'status': event.get_outcome_display(),
            'details': event.notes,
        })
    for appointment in appointments:
        timeline.append({
            'date': appointment.appointment_date,
            'type': 'Appointment',
            'title': appointment.get_visit_purpose_display(),
            'status': appointment.get_status_display(),
            'details': appointment.facility.name,
        })
    for referral in referrals:
        timeline.append({
            'date': referral.referred_on,
            'type': 'Referral',
            'title': referral.receiving_point_name,
            'status': referral.get_confirmation_status_display(),
            'details': referral.get_initiation_outcome_display(),
        })
    for task in follow_up_tasks:
        timeline.append({
            'date': task.due_date,
            'type': 'Follow-up',
            'title': task.get_reason_display(),
            'status': task.get_status_display(),
            'details': task.outcome_notes or task.notes,
        })
    timeline.sort(key=lambda item: item['date'], reverse=True)
    timeline_by_year = []
    year_lookup = {}
    for index, item in enumerate(timeline, start=1):
        item['index'] = index
        year = item['date'].year
        if year not in year_lookup:
            year_group = {
                'year': year,
                'items': [],
            }
            year_lookup[year] = year_group
            timeline_by_year.append(year_group)
        year_lookup[year]['items'].append(item)
    latest_item = timeline[0] if timeline else None
    first_item = timeline[-1] if timeline else None
    upcoming_appointment = (
        appointments
        .filter(status='upcoming', appointment_date__gte=timezone.localdate())
        .order_by('appointment_date', 'appointment_time')
        .first()
    )
    open_follow_up_count = follow_up_tasks.exclude(status__in=['completed', 'cancelled']).count()
    timeline_summary = {
        'total_items': len(timeline),
        'first_item': first_item,
        'latest_item': latest_item,
        'upcoming_appointment': upcoming_appointment,
        'open_follow_up_count': open_follow_up_count,
    }

    return render(request, 'users/my_journey.html', {
        'profile': profile,
        'locator': locator,
        'consent': consent,
        'appointments': appointments[:10],
        'journey_events': journey_events[:10],
        'referrals': referrals[:10],
        'follow_up_tasks': follow_up_tasks[:10],
        'timeline': timeline,
        'timeline_by_year': timeline_by_year,
        'timeline_summary': timeline_summary,
    })


@role_required(*USER_ADMIN_ROLES)
@never_cache
def user_management_stats(request):
    """Return user management summary counts for async cards."""
    return JsonResponse(get_user_management_stats())


@role_required(*USER_ADMIN_ROLES)
@never_cache
def user_management_rows(request):
    """Return filtered user table rows for async search."""
    search_term = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    users = get_user_management_rows(search_term, role_filter)
    html = render_to_string('users/_user_management_rows.html', {
        'users': users,
        'search_term': search_term,
        'role_filter': role_filter,
    })
    return JsonResponse({
        'html': html,
        'count': len(users),
    })


@role_required(*USER_ADMIN_ROLES)
def object_history_events(request, app_label, model_name, object_pk):
    """Return audit history rows for an object history modal."""
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        raise PermissionDenied

    if not should_audit_model(model):
        raise PermissionDenied

    events = AuditLog.objects.select_related('actor').filter(
        app_label=app_label,
        model_name=model._meta.model_name,
        object_pk=str(object_pk),
    ).order_by('-created_at')

    selected_date = parse_date(request.GET.get('date', '').strip())
    if selected_date:
        current_timezone = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(selected_date, time.min), current_timezone)
        day_end = day_start + timedelta(days=1)
        events = events.filter(created_at__gte=day_start, created_at__lt=day_end)

    try:
        page_number = max(int(request.GET.get('page', 1)), 1)
    except (TypeError, ValueError):
        page_number = 1

    raw_per_page = request.GET.get('per_page', '5')
    if raw_per_page == 'all':
        per_page = max(events.count(), 1)
        per_page_value = 'all'
    else:
        try:
            per_page = int(raw_per_page)
        except (TypeError, ValueError):
            per_page = 5

        per_page = per_page if per_page in {5, 10, 20, 50} else 5
        per_page_value = per_page

    paginator = Paginator(events, per_page)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages or 1)

    return JsonResponse({
        'events': [
            {
                'action': event.action,
                'action_label': event.get_action_display(),
                'actor': event.actor.username if event.actor else 'System',
                'actor_full_name': event.actor.get_full_name() if event.actor else '',
                'created_at': timezone.localtime(event.created_at).strftime('%b %d, %Y %H:%M:%S'),
                'object_repr': event.object_repr,
                'changes': [
                    {
                        'field': field,
                        'old': change.get('old') if isinstance(change, dict) else '',
                        'new': change.get('new') if isinstance(change, dict) else '',
                    }
                    for field, change in event.changes.items()
                ],
            }
            for event in page.object_list
        ],
        'pagination': {
            'page': page.number,
            'per_page': per_page_value,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,
            'has_previous': page.has_previous(),
            'has_next': page.has_next(),
        },
        'filters': {
            'date': selected_date.isoformat() if selected_date else '',
        },
    })


@active_login_required
def user_detail(request, pk):
    """Display detailed information about a specific user"""
    if request.user.pk != pk and not (
        request.user.is_superuser or get_user_role(request.user) in DASHBOARD_ROLES
    ):
        raise PermissionDenied

    user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    can_admin_edit = request.user.is_superuser or get_user_role(request.user) in USER_ADMIN_ROLES
    can_edit_profile = request.user.pk == user.pk or can_admin_edit
    edit_user_form = UserForm(instance=user)
    edit_profile_form = UserProfileForm(instance=profile) if can_admin_edit else SelfProfileForm(instance=profile)
    context = {
        'user': user,
        'profile': profile,
        'can_admin_edit_profile': can_admin_edit,
        'can_edit_profile': can_edit_profile,
        'edit_user_form': edit_user_form,
        'edit_profile_form': edit_profile_form,
    }
    return render(request, 'users/user_detail.html', context)


@active_login_required
def user_profile_update(request, pk):
    """Update a profile from the profile-page modal."""
    user = get_object_or_404(User, pk=pk)
    if request.user.pk != user.pk and not (
        request.user.is_superuser or get_user_role(request.user) in USER_ADMIN_ROLES
    ):
        raise PermissionDenied

    profile, _ = UserProfile.objects.get_or_create(user=user)
    can_admin_edit = request.user.is_superuser or get_user_role(request.user) in USER_ADMIN_ROLES

    if request.method != 'POST':
        return redirect('user_detail', pk=user.pk)

    if can_admin_edit:
        user_form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile)
    else:
        user_form = UserForm(request.POST, instance=user)
        profile_form = SelfProfileForm(request.POST, instance=profile)

    if user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile = profile_form.save()
        if not can_admin_edit and profile.person_identity_id:
            identity = profile.person_identity
            identity.full_name = user.get_full_name().strip() or user.username
            identity.phone = profile.phone or None
            identity.date_of_birth = profile.date_of_birth
            identity.save(update_fields=['full_name', 'phone', 'date_of_birth'])
        elif not profile.person_identity_id:
            profile.person_identity = PersonIdentity.for_user_defaults(
                user,
                phone=profile.phone or '',
                date_of_birth=profile.date_of_birth,
            )
            profile.save(update_fields=['person_identity'])

        messages.success(request, 'Profile updated successfully.')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'redirect': reverse('user_detail', args=[user.pk])})
        return redirect('user_detail', pk=user.pk)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        errors = {}
        for field, error_list in user_form.errors.items():
            errors[field] = list(error_list)
        for field, error_list in profile_form.errors.items():
            errors[field] = list(error_list)
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    for field, errors in user_form.errors.items():
        for error in errors:
            messages.error(request, f'User - {field}: {error}')
    for field, errors in profile_form.errors.items():
        for error in errors:
            messages.error(request, f'Profile - {field}: {error}')
    return redirect('user_detail', pk=user.pk)


@role_required(*USER_ADMIN_ROLES)
def user_create(request):
    """Create a new user"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        is_staff = request.POST.get('is_staff') == 'on'
        role = normalize_user_role_for_staff(request.POST.get('role'), is_staff)
        sex = request.POST.get('sex') or ''
        person_identity = get_selected_person_identity(request.POST.get('person_identity') or None)
        facility_id = request.POST.get('facility') or None
        population_group_id = request.POST.get('population_group') or None
        valid_roles = {choice[0] for choice in UserProfile.ROLE_CHOICES}
        role_error = None
        facility_error = None
        population_group_error = None
        facility = None
        population_group = None
        if role not in valid_roles:
            role_error = 'Select a valid staff role.' if is_staff else 'Select a valid role.'
        if role in FACILITY_REQUIRED_ROLES:
            if not facility_id:
                facility_error = 'Select the facility where this user works.'
            else:
                facility = Facility.objects.filter(pk=facility_id).first()
                if not facility:
                    facility_error = 'Select a valid facility.'
        elif facility_id and role in FACILITY_ASSIGNABLE_ROLES:
            facility = Facility.objects.filter(pk=facility_id).first()
            if not facility:
                facility_error = 'Select a valid facility.'
        if role == 'client' and population_group_id:
            population_group = PopulationGroup.objects.filter(pk=population_group_id, is_active=True).first()
            if not population_group:
                population_group_error = 'Select a valid population group.'
            elif not population_group_matches_sex(population_group, sex):
                population_group_error = 'Select a population group that is applicable to this client sex.'
        if form.is_valid():
            if role_error:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': {'role': [role_error]}})
                messages.error(request, role_error)
                return redirect('user_list')
            if facility_error:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': {'facility': [facility_error]}})
                messages.error(request, facility_error)
                return redirect('user_list')
            if population_group_error:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': {'population_group': [population_group_error]}})
                messages.error(request, population_group_error)
                return redirect('user_list')
            user = form.save()
            user.is_staff = is_staff
            user.save(update_fields=['is_staff'])
            user.profile.role = role
            user.profile.sex = sex
            user.profile.person_identity = person_identity or PersonIdentity.for_user_defaults(user)
            user.profile.facility = facility if role in FACILITY_ASSIGNABLE_ROLES else None
            user.profile.population_group = population_group if role == 'client' else None
            user.profile.must_change_password = request.POST.get('must_change_password') == 'on'
            user.profile.save(update_fields=[
                'role',
                'sex',
                'person_identity',
                'facility',
                'population_group',
                'must_change_password',
            ])
            
            # Handle AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'user_id': user.pk})
            
            messages.success(request, f'User "{user.username}" created successfully!')
            return redirect('user_detail', pk=user.pk)
        else:
            # Handle AJAX error responses
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {}
                for field, error_list in form.errors.items():
                    errors[field] = error_list
                if role_error:
                    errors['role'] = [role_error]
                if facility_error:
                    errors['facility'] = [facility_error]
                if population_group_error:
                    errors['population_group'] = [population_group_error]
                return JsonResponse({'success': False, 'errors': errors})
            
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            if role_error:
                messages.error(request, role_error)
            if facility_error:
                messages.error(request, facility_error)
            if population_group_error:
                messages.error(request, population_group_error)
    else:
        form = UserCreationForm()
    
    context = {
        'form': form,
        'title': 'Create New User',
    }
    return render(request, 'users/user_form.html', context)


@role_required(*USER_ADMIN_ROLES)
def user_edit(request, pk):
    """Edit an existing user"""
    user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        is_staff = request.POST.get('is_staff') == 'on'
        post_data = request.POST.copy()
        post_data['role'] = normalize_user_role_for_staff(post_data.get('role'), is_staff)
        role_error = None
        if post_data['role'] not in {choice[0] for choice in UserProfile.ROLE_CHOICES}:
            role_error = 'Select a valid staff role.' if is_staff else 'Select a valid role.'
        user_form = UserForm(post_data, instance=user)
        profile_form = UserProfileForm(post_data, instance=profile)
        
        if user_form.is_valid() and profile_form.is_valid() and not role_error:
            user_form.save()
            user.is_staff = is_staff
            user.save(update_fields=['is_staff'])
            profile = profile_form.save()
            if not profile.person_identity_id:
                profile.person_identity = PersonIdentity.for_user_defaults(
                    user,
                    phone=profile.phone or '',
                    date_of_birth=profile.date_of_birth,
                )
                profile.save(update_fields=['person_identity'])
            
            # Handle AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            
            messages.success(request, f'User "{user.username}" updated successfully!')
            return redirect('user_detail', pk=user.pk)
        else:
            # Handle AJAX error responses
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {}
                for field, error_list in user_form.errors.items():
                    errors[field] = error_list
                for field, error_list in profile_form.errors.items():
                    errors[field] = error_list
                if role_error:
                    errors['role'] = [role_error]
                return JsonResponse({'success': False, 'errors': errors})
            
            for field, errors in user_form.errors.items():
                for error in errors:
                    messages.error(request, f"User - {field}: {error}")
            for field, errors in profile_form.errors.items():
                for error in errors:
                    messages.error(request, f"Profile - {field}: {error}")
            if role_error:
                messages.error(request, role_error)
    else:
        user_form = UserForm(instance=user)
        profile_form = UserProfileForm(instance=profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'user': user,
        'title': f'Edit {user.username}',
    }
    return render(request, 'users/user_edit.html', context)


@require_POST
@role_required(*USER_ADMIN_ROLES)
def user_reset_password(request, pk):
    """Generate a temporary password and email it to the user."""
    user = get_object_or_404(User, pk=pk)
    if not user.email:
        return JsonResponse({
            'success': False,
            'errors': {
                'email': ['This user does not have an email address.'],
            },
        }, status=400)

    temporary_password = generate_temporary_password()
    expires_at = timezone.now() + TEMPORARY_PASSWORD_TTL
    user.set_password(temporary_password)
    user.profile.must_change_password = request.POST.get('must_change_password') == 'on'
    user.profile.temporary_password_expires_at = expires_at
    user.profile.save(update_fields=['must_change_password', 'temporary_password_expires_at'])
    user.save(update_fields=['password'])
    sessions_invalidated = logout_user_sessions(user)

    if settings.DEBUG:
        logger.warning(
            'Temporary password generated for user "%s" <%s>: %s',
            user.get_username(),
            user.email,
            temporary_password,
        )
    else:
        logger.info(
            'Temporary password generated for user "%s" <%s>; password hidden because DEBUG is off.',
            user.get_username(),
            user.email,
        )

    send_mail(
        subject='Your MyThanzi password has been reset',
        message=(
            f'Hello {user.get_username()},\n\n'
            'An administrator reset your MyThanzi password.\n\n'
            f'Temporary password: {temporary_password}\n\n'
            'This temporary password is valid for 10 minutes.\n\n'
            'Please sign in and change this password as soon as possible.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return JsonResponse({
        'success': True,
        'email': user.email,
        'sessions_invalidated': sessions_invalidated,
        'expires_in_minutes': int(TEMPORARY_PASSWORD_TTL.total_seconds() // 60),
    })


@role_required(*USER_ADMIN_ROLES)
def user_delete(request, pk):
    """Delete a user"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        username = user.username
        user.delete()
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        messages.success(request, f'User "{username}" deleted successfully!')
        return redirect('user_list')
    
    context = {
        'user': user,
    }
    return render(request, 'users/user_confirm_delete.html', context)


@role_required(*DASHBOARD_ROLES)
def user_dashboard(request):
    """Administrative dashboard for core portal areas."""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    recent_users = User.objects.all().order_by('-date_joined')[:5]
    total_facilities = Facility.objects.count()
    mapped_facilities = Facility.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
    total_appointments = Appointment.objects.count()
    now = timezone.localtime()
    upcoming_filter = (
        Q(appointment_date__gt=now.date()) |
        Q(appointment_date=now.date(), appointment_time__gt=now.time())
    )
    
    role_counts = UserProfile.objects.values('role').annotate(count=Count('pk'))
    role_stats = [
        {
            'role': role_key,
            'label': role_label,
            'count': next((item['count'] for item in role_counts if item['role'] == role_key), 0),
        }
        for role_key, role_label in UserProfile.ROLE_CHOICES
    ]
    dashboard_cards = [
        {
            'title': 'Users',
            'icon': 'manage_accounts',
            'value': total_users,
            'meta': f'{active_users} active, {inactive_users} inactive',
            'href': reverse('user_list'),
        },
        {
            'title': 'Locations',
            'icon': 'map',
            'value': total_facilities,
            'meta': f'{Province.objects.count()} provinces, {District.objects.count()} districts',
            'href': reverse('location_management'),
        },
        {
            'title': 'Mapped Facilities',
            'icon': 'location_on',
            'value': mapped_facilities,
            'meta': f'{max(total_facilities - mapped_facilities, 0)} still need coordinates',
            'href': f"{reverse('location_management_tab', kwargs={'tab': 'facilities'})}?mapped=unmapped",
        },
        {
            'title': 'Appointments',
            'icon': 'calendar_month',
            'value': total_appointments,
            'meta': f"{Appointment.objects.filter(status='upcoming').filter(upcoming_filter).count()} upcoming",
            'href': reverse('appointment_list'),
        },
    ]
    
    context = {
        'dashboard_cards': dashboard_cards,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'recent_users': recent_users,
        'role_stats': role_stats,
        'recent_audit_events': AuditLog.objects.select_related('actor')[:5],
    }
    return render(request, 'users/dashboard.html', context)


@active_login_required
def appointment_list(request):
    """Display, filter, and create appointments."""
    can_manage = can_manage_appointments(request.user)
    valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES} | {'all'}
    selected_status = request.GET.get('status', 'all').strip()
    search_term = request.GET.get('q', '').strip()
    selected_month = request.GET.get('month', '').strip()

    if selected_status not in valid_statuses:
        selected_status = 'all'

    today = timezone.localdate()
    try:
        calendar_year, calendar_month = [int(part) for part in selected_month.split('-', 1)]
        calendar_start = date(calendar_year, calendar_month, 1)
    except (TypeError, ValueError):
        calendar_start = today.replace(day=1)

    now = timezone.localtime()
    future_appointment_filter = (
        Q(appointment_date__gt=now.date()) |
        Q(appointment_date=now.date(), appointment_time__gt=now.time())
    )
    _, days_in_month = calendar.monthrange(calendar_start.year, calendar_start.month)
    calendar_end = calendar_start.replace(day=days_in_month)
    previous_month = (calendar_start - timedelta(days=1)).replace(day=1)
    next_month = (calendar_end + timedelta(days=1)).replace(day=1)

    form = AppointmentForm(request.POST or None, created_by=request.user)
    if request.method == 'POST' and not can_manage:
        raise PermissionDenied
    if request.method == 'POST' and form.is_valid():
        appointment = form.save()
        portal_notification, email_notification = notify_appointment_created(appointment, actor=request.user)
        messages.success(
            request,
            f'Appointment for "{appointment.beneficiary.username}" booked successfully!'
        )
        if email_notification and email_notification.status == 'failed':
            messages.warning(request, 'The portal notification was created, but the email notification could not be sent.')
        elif portal_notification and not appointment.beneficiary.email:
            messages.warning(request, 'The portal notification was created. No email was sent because the client has no email address.')
        return redirect('appointment_list')

    appointments = get_visible_appointments(request.user)
    appointment_clients = [
        {
            'id': client.pk,
            'name': client.get_full_name().strip() or client.username,
            'phone': client.profile.phone or '',
        }
        for client in User.objects.select_related('profile').filter(
            profile__role='client',
            profile__is_active=True,
            is_active=True,
        ).order_by('first_name', 'last_name', 'username')
    ]
    appointment_facilities = [
        {
            'id': facility.pk,
            'name': facility.name,
            'district': facility.district.name,
            'province': facility.district.province.name,
            'services': [service.code for service in facility.services.all() if service.is_active],
        }
        for facility in Facility.objects.select_related('district__province').prefetch_related('services').order_by(
            'district__province__name',
            'district__name',
            'name',
        )
    ]

    if selected_status == 'upcoming':
        appointments = appointments.filter(status='upcoming').filter(future_appointment_filter)
    elif selected_status != 'all':
        appointments = appointments.filter(status=selected_status)

    if search_term:
        appointments = appointments.filter(
            Q(beneficiary__username__icontains=search_term) |
            Q(beneficiary__profile__reference_number__icontains=search_term) |
            Q(beneficiary__first_name__icontains=search_term) |
            Q(beneficiary__last_name__icontains=search_term) |
            Q(beneficiary__email__icontains=search_term) |
            Q(beneficiary__profile__phone__icontains=search_term) |
            Q(facility__name__icontains=search_term) |
            Q(district__name__icontains=search_term) |
            Q(province__name__icontains=search_term)
        )

    month_appointments = appointments.filter(
        appointment_date__gte=calendar_start,
        appointment_date__lte=calendar_end,
    ).order_by('appointment_date', 'appointment_time')
    appointments_by_date = {}
    for appointment in month_appointments:
        appointments_by_date.setdefault(appointment.appointment_date, []).append(appointment)

    calendar_weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(calendar_start.year, calendar_start.month):
        calendar_weeks.append([
            {
                'date': day,
                'in_month': day.month == calendar_start.month,
                'is_today': day == today,
                'is_past': day < today,
                'appointments': appointments_by_date.get(day, []),
            }
            for day in week
        ])

    context = {
        'appointments': appointments,
        'calendar_weeks': calendar_weeks,
        'calendar_month': calendar_start,
        'calendar_month_value': calendar_start.strftime('%Y-%m'),
        'previous_month_value': previous_month.strftime('%Y-%m'),
        'next_month_value': next_month.strftime('%Y-%m'),
        'weekday_labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'month_appointment_count': month_appointments.count(),
        'form': form,
        'appointment_clients': appointment_clients,
        'appointment_facilities': appointment_facilities,
        'form_has_errors': request.method == 'POST' and form.errors,
        'appointment_services': Service.objects.filter(is_active=True).order_by('name'),
        'can_manage_appointments': can_manage,
        'is_client_appointment_view': get_user_role(request.user) == 'client',
        'search_term': search_term,
        'selected_status': selected_status,
        'stats': {
            'total': get_visible_appointments(request.user).count(),
            'upcoming': get_visible_appointments(request.user).filter(status='upcoming').filter(future_appointment_filter).count(),
            'completed': get_visible_appointments(request.user).filter(status='completed').count(),
            'missed': get_visible_appointments(request.user).filter(status='missed').count(),
        },
    }
    return render(request, 'users/appointments.html', context)


@role_required(*APPOINTMENT_ROLES)
def appointment_edit(request, pk):
    """Edit an appointment from the calendar action modal."""
    appointment = get_object_or_404(get_visible_appointments(request.user), pk=pk)
    form = AppointmentEditForm(
        request.POST or None,
        instance=appointment,
    )

    next_url = request.POST.get('next') or request.GET.get('next') or reverse('appointment_list')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('appointment_list')

    if request.method == 'POST' and form.is_valid():
        updated_appointment = form.save()
        messages.success(
            request,
            f'Appointment for "{updated_appointment.beneficiary.username}" updated successfully.'
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'redirect': next_url})
        return redirect(next_url)

    context = {
        'appointment': appointment,
        'form': form,
        'next_url': next_url,
    }
    status = 400 if request.method == 'POST' else 200
    return render(request, 'users/_appointment_edit_form.html', context, status=status)


@require_POST
@role_required(*APPOINTMENT_ROLES)
def appointment_update_status(request, pk):
    """Update an appointment status from the calendar action modal."""
    appointment = get_object_or_404(get_visible_appointments(request.user), pk=pk)
    status_value = request.POST.get('status', '').strip()
    valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}
    if status_value not in valid_statuses:
        messages.error(request, 'Choose a valid appointment action.')
    else:
        appointment.status = status_value
        appointment.save(update_fields=['status', 'updated_at'])
        messages.success(
            request,
            f'Appointment for "{appointment.beneficiary.username}" marked as {appointment.get_status_display().lower()}.'
        )

    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('appointment_list')
