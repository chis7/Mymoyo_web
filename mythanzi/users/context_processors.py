from .models import Notification


def portal_notifications(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'portal_unread_notifications_count': 0,
            'portal_recent_notifications': [],
        }

    notifications = Notification.objects.filter(
        recipient=request.user,
        channel='portal',
    )
    return {
        'portal_unread_notifications_count': notifications.filter(
            read_at__isnull=True,
        ).count(),
        'portal_recent_notifications': notifications[:5],
    }
