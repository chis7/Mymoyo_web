import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Notification, NotificationTypeSetting

logger = logging.getLogger(__name__)


def appointment_notification_content(appointment):
    client_name = appointment.beneficiary.get_full_name().strip() or appointment.beneficiary.username
    when = f'{appointment.appointment_date:%d %b %Y} at {appointment.appointment_time:%H:%M}'
    purpose = appointment.get_visit_purpose_display()
    facility = appointment.facility.name
    title = 'Appointment booked'
    message = (
        f'Your {purpose.lower()} appointment has been booked for {when} at {facility}.'
    )
    email_subject = f'MyThanzi appointment: {when}'
    email_body = (
        f'Hello {client_name},\n\n'
        f'{message}\n\n'
        f'Facility: {appointment.facility.name}\n'
        f'District: {appointment.district.name}\n'
        f'Province: {appointment.province.name}\n\n'
        'Please log in to MyThanzi to view the appointment in your portal.\n'
    )
    return title, message, email_subject, email_body


def notify_appointment_created(appointment, actor=None):
    """Create portal and email notifications for a newly booked appointment."""
    setting = NotificationTypeSetting.objects.filter(key='appointment').first()
    if setting and not setting.enabled:
        return None, None

    title, message, email_subject, email_body = appointment_notification_content(appointment)

    portal_notification = None
    should_send_portal = setting.portal_enabled if setting else True
    should_send_email = setting.email_enabled if setting else True

    if should_send_portal:
        portal_notification = Notification.objects.create(
            recipient=appointment.beneficiary,
            actor=actor or appointment.created_by,
            appointment=appointment,
            notification_type='appointment',
            channel='portal',
            status='sent',
            title=title,
            message=message,
            sent_at=timezone.now(),
        )

    email_notification = None
    if should_send_email and appointment.beneficiary.email:
        email_notification = Notification.objects.create(
            recipient=appointment.beneficiary,
            actor=actor or appointment.created_by,
            appointment=appointment,
            notification_type='appointment',
            channel='email',
            status='queued',
            title=email_subject,
            message=email_body,
        )
        try:
            send_mail(
                subject=email_subject,
                message=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[appointment.beneficiary.email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception('Appointment email notification failed for appointment %s', appointment.pk)
            email_notification.status = 'failed'
            email_notification.error_message = str(exc)
            email_notification.save(update_fields=['status', 'error_message', 'updated_at'])
        else:
            email_notification.status = 'sent'
            email_notification.sent_at = timezone.now()
            email_notification.save(update_fields=['status', 'sent_at', 'updated_at'])

    return portal_notification, email_notification
