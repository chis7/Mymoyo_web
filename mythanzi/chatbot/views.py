import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from .local_content import build_local_context, get_local_link_ids, get_local_reply
from users.access import active_login_required


SYSTEM_PROMPT = """
You are the MyThanzi portal support assistant. Help users understand portal
navigation, user roles, appointments, and general use of the application.
You also have local MyThanzi health education content. Use it to explain
self-testing, risk screening, clinic search, medication reminders, side
effects, privacy, and appointment follow-up.
Keep answers concise and practical. Do not provide diagnosis, treatment
recommendations, or emergency medical guidance. If asked for medical advice,
tell the user to contact a qualified healthcare professional. Never reveal
private information about other users or claim to have changed portal data.
When a user asks where to find something in the app, explain the path in the
side menu or account menu. Relevant page buttons may be shown with your answer,
so refer to them naturally instead of writing raw URLs.
""".strip()


APP_LINKS = {
    'home': {
        'label': 'Home',
        'route': 'portal_home',
    },
    'dashboard': {
        'label': 'Command Center',
        'route': 'user_dashboard',
        'roles': {'admin', 'supervisor'},
        'allow_superuser': True,
    },
    'appointments': {
        'label': 'Appointments',
        'route': 'appointment_list',
        'roles': {'admin', 'supervisor', 'provider', 'chw', 'mobiliser'},
        'allow_superuser': True,
    },
    'profile': {
        'label': 'My Profile',
        'route': 'user_detail',
        'user_pk': True,
    },
    'manage_users': {
        'label': 'Manage Users',
        'route': 'user_list',
        'roles': {'admin'},
        'allow_superuser': True,
    },
    'facility_map': {
        'label': 'Find a Clinic',
        'route': 'facility_map',
    },
    'admin_panel': {
        'label': 'Admin Panel',
        'route': 'admin:index',
        'staff_only': True,
    },
}


def _extract_output_text(response_data):
    for item in response_data.get('output', []):
        for content in item.get('content', []):
            if content.get('type') == 'output_text':
                return content.get('text', '').strip()
    return ''


def _clean_history(history):
    cleaned_history = []
    if not isinstance(history, list):
        return cleaned_history

    for item in history[-10:]:
        if not isinstance(item, dict) or item.get('role') not in {'user', 'assistant'}:
            continue

        content = str(item.get('content', '')).strip()[:1000]
        if content:
            cleaned_history.append({'role': item['role'], 'content': content})

    return cleaned_history


def _user_role(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', '')


def _user_can_access_link(user, link_config):
    if link_config.get('staff_only') and not user.is_staff:
        return False

    allowed_roles = link_config.get('roles')
    if not allowed_roles:
        return True

    if link_config.get('allow_superuser') and user.is_superuser:
        return True

    return _user_role(user) in allowed_roles


def _resolve_app_link(user, link_id):
    link_config = APP_LINKS.get(link_id)
    if not link_config or not _user_can_access_link(user, link_config):
        return None

    kwargs = {}
    if link_config.get('user_pk'):
        kwargs['pk'] = user.pk

    try:
        url = reverse(link_config['route'], kwargs=kwargs or None)
    except NoReverseMatch:
        return None

    return {
        'label': link_config['label'],
        'url': url,
    }


def _build_app_links(message, user):
    links = []
    for link_id in get_local_link_ids(message):
        resolved_link = _resolve_app_link(user, link_id)
        if resolved_link and resolved_link not in links:
            links.append(resolved_link)
    return links


def _offline_response(message, user):
    return JsonResponse({
        'reply': get_local_reply(message),
        'mode': 'offline',
        'links': _build_app_links(message, user),
    })


@require_POST
@active_login_required
def chat_message(request):
    try:
        request_data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Send a valid message.'}, status=400)

    message = str(request_data.get('message', '')).strip()[:1000]
    if not message:
        return JsonResponse({'error': 'Enter a message first.'}, status=400)

    if not settings.OPENAI_API_KEY:
        return _offline_response(message, request.user)

    input_messages = _clean_history(request_data.get('history'))
    input_messages.append({'role': 'user', 'content': message})
    app_links = _build_app_links(message, request.user)
    app_link_context = '\n'.join(f"- {link['label']}: {link['url']}" for link in app_links) or 'None'
    payload = json.dumps({
        'model': settings.OPENAI_CHATBOT_MODEL,
        'instructions': (
            f"{SYSTEM_PROMPT}\n\n"
            f"Local MyThanzi content:\n{build_local_context()}\n\n"
            f"Relevant resolved app links for this user:\n{app_link_context}"
        ),
        'input': input_messages,
    }).encode('utf-8')
    api_request = Request(
        'https://api.openai.com/v1/responses',
        data=payload,
        headers={
            'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urlopen(api_request, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError):
        return _offline_response(message, request.user)

    reply = _extract_output_text(response_data)
    if not reply:
        return _offline_response(message, request.user)

    return JsonResponse({
        'reply': reply,
        'mode': 'online',
        'links': app_links,
    })
