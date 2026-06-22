LOCAL_KNOWLEDGE = [
    {
        'title': 'Using MyThanzi',
        'keywords': {'portal', 'mythanzi', 'profile', 'dashboard', 'navigate', 'navigation', 'account'},
        'links': {'home', 'dashboard', 'profile'},
        'answer': (
            'Use MyThanzi to view your profile, appointments, '
            'clinic information, and available self-service tools. Use the side menu to move '
            'between sections, and use your account menu for profile, theme, and logout actions.'
        ),
    },
    {
        'title': 'Appointments',
        'keywords': {'appointment', 'appointments', 'booking', 'book', 'visit', 'missed', 'upcoming'},
        'links': {'appointments'},
        'answer': (
            'The Appointments area helps permitted users view, book, and track visits. '
            'Upcoming, completed, and missed tabs separate records by status. If a visit is missed, '
            'follow your clinic or programme guidance for rebooking or follow-up.'
        ),
    },
    {
        'title': 'Find a Clinic',
        'keywords': {'clinic', 'facility', 'map', 'district', 'province', 'location'},
        'links': {'facility_map'},
        'answer': (
            'Use Find a Clinic to search facilities by clinic name, district, province, or MFL code. '
            'You can filter by location and open matching clinic results from the map/list view.'
        ),
    },
    {
        'title': 'User Roles',
        'keywords': {'role', 'roles', 'admin', 'provider', 'client', 'chw', 'mobiliser', 'supervisor'},
        'links': {'manage_users', 'profile'},
        'answer': (
            'MyThanzi uses roles to show the right tools to each person. Clients see their own care '
            'information, providers and CHWs support appointments and follow-up, supervisors monitor '
            'work, and admins manage users and reference data.'
        ),
    },
    {
        'title': 'Self Testing',
        'keywords': {'self-test', 'selftest', 'test', 'testing', 'hiv'},
        'links': {'facility_map'},
        'answer': (
            'For self-testing, follow the instructions provided with the approved test kit. '
            'If your result is reactive, unclear, or worrying, contact a clinic or qualified health '
            'worker for confirmatory testing and next steps.'
        ),
    },
    {
        'title': 'Risk Screening',
        'keywords': {'risk', 'screening', 'assessment', 'prevention', 'protect'},
        'links': {'facility_map'},
        'answer': (
            'Risk screening helps identify prevention or follow-up needs. Answer screening questions '
            'honestly so a health worker can guide you to appropriate services. This assistant can explain '
            'portal features, but it cannot diagnose or replace professional care.'
        ),
    },
    {
        'title': 'Medication Reminders',
        'keywords': {'medication', 'medicine', 'reminder', 'reminders', 'dose', 'adherence'},
        'links': {'appointments', 'facility_map'},
        'answer': (
            'Medication reminders are meant to support routine care and adherence. If you miss a dose, '
            'have side effects, or are unsure what to do, contact your clinic or a qualified health worker.'
        ),
    },
    {
        'title': 'Side Effects',
        'keywords': {'side', 'effects', 'effect', 'reaction', 'symptom', 'symptoms', 'adverse'},
        'links': {'facility_map', 'appointments'},
        'answer': (
            'If you experience side effects, report them through the portal if available and contact your '
            'clinic. Seek urgent help for severe symptoms such as trouble breathing, swelling, fainting, '
            'severe rash, chest pain, or any emergency concern.'
        ),
    },
    {
        'title': 'Privacy',
        'keywords': {'privacy', 'private', 'confidential', 'password', 'security', 'data'},
        'links': {'profile'},
        'answer': (
            'Keep your password private and log out on shared devices. MyThanzi limits access by role, '
            'so users should only see information permitted for their work or care relationship.'
        ),
    },
]


LOCAL_FALLBACK = (
    'I can help offline with MyThanzi navigation, appointments, clinic search, roles, self-testing, '
    'risk screening, medication reminders, side effects, and privacy. Try asking about one of those topics. '
    'For personal medical advice or emergencies, contact a qualified health worker or emergency service.'
)


def _score_items(message):
    normalized_message = str(message or '').lower()
    scored_items = []

    for item in LOCAL_KNOWLEDGE:
        score = sum(1 for keyword in item['keywords'] if keyword in normalized_message)
        if score:
            scored_items.append((score, item))

    scored_items.sort(key=lambda match: match[0], reverse=True)
    return scored_items


def build_local_context():
    context_items = []
    for item in LOCAL_KNOWLEDGE:
        links = ', '.join(sorted(item.get('links', []))) or 'none'
        context_items.append(f"{item['title']}: {item['answer']} Relevant app links: {links}.")
    return '\n\n'.join(context_items)


def get_local_link_ids(message):
    scored_items = _score_items(message)
    if not scored_items:
        return []

    link_ids = []
    for score, item in scored_items:
        if score < scored_items[0][0]:
            continue
        for link_id in item.get('links', []):
            if link_id not in link_ids:
                link_ids.append(link_id)
    return link_ids


def get_local_reply(message):
    scored_items = _score_items(message)
    if not scored_items:
        return LOCAL_FALLBACK

    best_item = scored_items[0][1]
    return f"{best_item['answer']}\n\nOffline guide: this answer uses local MyThanzi education content."
