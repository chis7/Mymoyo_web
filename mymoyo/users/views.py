from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.apps import apps
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.urls import reverse
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .models import Appointment, AuditLog, UserProfile
from .audit import should_audit_model
from .forms import (
    AppointmentForm,
    ClinicFeedbackForm,
    PublicRegistrationForm,
    SideEffectReportForm,
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
    get_user_role,
    role_required,
)
from locations.models import Province, District, Facility


TEMPORARY_PASSWORD_TTL = timedelta(minutes=10)


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


def get_user_management_stats():
    logged_in_user_ids = get_logged_in_user_ids()
    return {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'inactive': User.objects.filter(is_active=False).count(),
        'logged_in': len(logged_in_user_ids),
    }


def get_user_management_rows(search_term='', role_filter=''):
    users = User.objects.prefetch_related('profile').order_by('-date_joined')

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
            if profile.must_change_password:
                return redirect('password_change_required')
            next_url = request.POST.get('next', '')
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('portal_home')

    return render(request, 'users/login.html', {
        'form': form,
        'next': request.POST.get('next') or request.GET.get('next', ''),
    })


def register_view(request):
    """Create a public client account and sign the user in."""
    if request.user.is_authenticated:
        return redirect('portal_home')

    form = PublicRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        user.profile.role = 'client'
        user.profile.is_active = True
        user.profile.save(update_fields=['role', 'is_active'])
        auth_login(request, user)
        messages.success(request, 'Your account has been created successfully.')
        return redirect('portal_home')

    return render(request, 'users/register.html', {'form': form})


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
    role = get_user_role(request.user)
    if role in DASHBOARD_ROLES:
        return redirect('user_dashboard')
    if role in APPOINTMENT_ROLES:
        return redirect('appointment_list')
    return redirect('user_detail', pk=request.user.pk)


@active_login_required
def medication_reminders(request):
    prevention_methods = [
        {
            'name': 'Oral PrEP (Daily Pill)',
            'schedule': 'Daily',
            'icon': 'pill',
            'status': 'Available',
        },
        {
            'name': 'CAB-LA Injectable',
            'schedule': 'Every 2 months',
            'icon': 'vaccines',
            'status': 'Available',
        },
        {
            'name': 'Dapivirine Ring',
            'schedule': 'Monthly',
            'icon': 'radio_button_unchecked',
            'status': 'Available',
        },
        {
            'name': 'Lenacapavir Injectable (LEN)',
            'schedule': 'Every 6 months',
            'icon': 'vaccines',
            'status': 'Available',
        },
        {
            'name': 'Event-Driven PrEP',
            'schedule': 'Before and after sex',
            'icon': 'bolt',
            'status': 'Available',
        },
    ]

    return render(request, 'users/medication_reminders.html', {
        'prevention_methods': prevention_methods,
    })


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


@active_login_required
def self_risk_assessment(request):
    result = None
    form = SelfRiskAssessmentForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        result = calculate_self_risk_assessment(form.cleaned_data)

    return render(request, 'users/self_risk_assessment.html', {
        'form': form,
        'result': result,
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


@active_login_required
def self_test_report(request):
    guidance = None
    form = SelfTestReportForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_self_test_guidance(form.cleaned_data)

    return render(request, 'users/self_test_report.html', {
        'form': form,
        'guidance': guidance,
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


@active_login_required
def side_effect_report(request):
    guidance = None
    form = SideEffectReportForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_side_effect_guidance(form.cleaned_data)

    return render(request, 'users/side_effect_report.html', {
        'form': form,
        'guidance': guidance,
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


@active_login_required
def clinic_feedback(request):
    guidance = None
    form = ClinicFeedbackForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        guidance = get_clinic_feedback_guidance(form.cleaned_data)

    return render(request, 'users/clinic_feedback.html', {
        'form': form,
        'guidance': guidance,
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
    }
    return render(request, 'users/user_management.html', context)


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
    context = {
        'user': user,
        'profile': profile,
    }
    return render(request, 'users/user_detail.html', context)


@role_required(*USER_ADMIN_ROLES)
def user_create(request):
    """Create a new user"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = request.POST.get('role')
            valid_roles = {choice[0] for choice in UserProfile.ROLE_CHOICES}
            if role in valid_roles:
                user.profile.role = role
            user.profile.must_change_password = request.POST.get('must_change_password') == 'on'
            user.profile.save(update_fields=['role', 'must_change_password'])
            
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
                return JsonResponse({'success': False, 'errors': errors})
            
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
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
        user_form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            
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
                return JsonResponse({'success': False, 'errors': errors})
            
            for field, errors in user_form.errors.items():
                for error in errors:
                    messages.error(request, f"User - {field}: {error}")
            for field, errors in profile_form.errors.items():
                for error in errors:
                    messages.error(request, f"Profile - {field}: {error}")
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

    send_mail(
        subject='Your MyMoyo password has been reset',
        message=(
            f'Hello {user.get_username()},\n\n'
            'An administrator reset your MyMoyo password.\n\n'
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
    """User management dashboard"""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    inactive_users = User.objects.filter(is_active=False).count()
    recent_users = User.objects.all().order_by('-date_joined')[:5]
    
    role_counts = UserProfile.objects.values('role').annotate(count=Count('pk'))
    role_stats = [
        {
            'role': role_key,
            'label': role_label,
            'count': next((item['count'] for item in role_counts if item['role'] == role_key), 0),
        }
        for role_key, role_label in UserProfile.ROLE_CHOICES
    ]
    
    context = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'recent_users': recent_users,
        'role_stats': role_stats,
    }
    return render(request, 'users/dashboard.html', context)


@role_required(*APPOINTMENT_ROLES)
def appointment_list(request):
    """Display, filter, and create appointments."""
    valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}
    selected_status = request.GET.get('status', 'upcoming').strip()
    search_term = request.GET.get('q', '').strip()

    if selected_status not in valid_statuses:
        selected_status = 'upcoming'

    form = AppointmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        appointment = form.save()
        messages.success(
            request,
            f'Appointment for "{appointment.beneficiary.username}" booked successfully!'
        )
        return redirect('appointment_list')

    appointments = Appointment.objects.select_related(
        'beneficiary',
        'province',
        'district',
        'facility',
    ).filter(status=selected_status)

    if search_term:
        appointments = appointments.filter(
            Q(beneficiary__username__icontains=search_term) |
            Q(beneficiary__first_name__icontains=search_term) |
            Q(beneficiary__last_name__icontains=search_term) |
            Q(beneficiary__email__icontains=search_term) |
            Q(facility__name__icontains=search_term) |
            Q(district__name__icontains=search_term) |
            Q(province__name__icontains=search_term)
        )

    context = {
        'appointments': appointments,
        'form': form,
        'form_has_errors': request.method == 'POST' and form.errors,
        'provinces': Province.objects.all(),
        'districts': District.objects.select_related('province').all(),
        'facilities': Facility.objects.select_related('district').all(),
        'search_term': search_term,
        'selected_status': selected_status,
        'stats': {
            'total': Appointment.objects.count(),
            'upcoming': Appointment.objects.filter(status='upcoming').count(),
            'completed': Appointment.objects.filter(status='completed').count(),
            'missed': Appointment.objects.filter(status='missed').count(),
        },
    }
    return render(request, 'users/appointments.html', context)
