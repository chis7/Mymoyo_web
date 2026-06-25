from .models import Notification


def portal_notifications(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'portal_unread_notifications_count': 0,
        }

    return {
        'portal_unread_notifications_count': Notification.objects.filter(
            recipient=request.user,
            channel='portal',
            read_at__isnull=True,
        ).count(),
    }
