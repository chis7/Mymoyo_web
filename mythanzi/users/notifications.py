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


def _display_name(user):
    return user.get_full_name().strip() or user.username


def _get_setting(key):
    return NotificationTypeSetting.objects.filter(key=key).first()


def send_configured_notification(
    *,
    key,
    recipient,
    title,
    message,
    actor=None,
    appointment=None,
    email_subject=None,
    email_body=None,
):
    """Send a notification using the configured channel for the notification type."""
    setting = _get_setting(key)
    if setting and not setting.enabled:
        return None, None

    portal_notification = None
    should_send_portal = setting.portal_enabled if setting else True
    should_send_email = setting.email_enabled if setting else True

    if should_send_portal:
        portal_notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            appointment=appointment,
            notification_type=key,
            channel='portal',
            status='sent',
            title=title,
            message=message,
            sent_at=timezone.now(),
        )

    email_notification = None
    if should_send_email and recipient.email:
        email_subject = email_subject or f'MyThanzi notification: {title}'
        email_body = email_body or f'Hello {_display_name(recipient)},\n\n{message}\n\nPlease log in to MyThanzi to view this update.\n'
        email_notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            appointment=appointment,
            notification_type=key,
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
            logger.exception('Email notification failed for %s to user %s', key, recipient.pk)
            email_notification.status = 'failed'
            email_notification.error_message = str(exc)
            email_notification.save(update_fields=['status', 'error_message', 'updated_at'])
        else:
            email_notification.status = 'sent'
            email_notification.sent_at = timezone.now()
            email_notification.save(update_fields=['status', 'sent_at', 'updated_at'])

    return portal_notification, email_notification


def notify_appointment_created(appointment, actor=None):
    """Create portal and email notifications for a newly booked appointment."""
    title, message, email_subject, email_body = appointment_notification_content(appointment)
    return send_configured_notification(
        key='appointment',
        recipient=appointment.beneficiary,
        actor=actor or appointment.created_by,
        appointment=appointment,
        title=title,
        message=message,
        email_subject=email_subject,
        email_body=email_body,
    )


def notify_appointment_updated(appointment, actor=None):
    title = 'Appointment updated'
    message = (
        f'Your {appointment.get_visit_purpose_display().lower()} appointment is now scheduled for '
        f'{appointment.appointment_date:%d %b %Y} at {appointment.appointment_time:%H:%M} '
        f'at {appointment.facility.name}. Status: {appointment.get_status_display()}.'
    )
    return send_configured_notification(
        key='appointment',
        recipient=appointment.beneficiary,
        actor=actor or appointment.created_by,
        appointment=appointment,
        title=title,
        message=message,
        email_subject='MyThanzi appointment updated',
    )


def notify_appointment_deleted(appointment, actor=None):
    title = 'Appointment cancelled'
    message = (
        f'Your {appointment.get_visit_purpose_display().lower()} appointment for '
        f'{appointment.appointment_date:%d %b %Y} at {appointment.appointment_time:%H:%M} '
        f'at {appointment.facility.name} has been removed.'
    )
    return send_configured_notification(
        key='appointment',
        recipient=appointment.beneficiary,
        actor=actor or appointment.created_by,
        title=title,
        message=message,
        email_subject='MyThanzi appointment cancelled',
    )


def notify_journey_event_created(event, actor=None):
    client_name = _display_name(event.client)
    title = 'Journey updated'
    message = (
        f'Your journey was updated: {event.get_stage_display()} marked as '
        f'{event.get_outcome_display().lower()} on {event.event_date:%d %b %Y}.'
    )
    return send_configured_notification(
        key='client_journey_event',
        recipient=event.client,
        actor=actor or event.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi journey update',
        email_body=f'Hello {client_name},\n\n{message}\n\nPlease log in to MyThanzi to view your journey timeline.\n',
    )


def notify_journey_event_updated(event, actor=None):
    title = 'Journey event updated'
    message = (
        f'Your {event.get_stage_display()} journey event was updated. '
        f'Current status: {event.get_outcome_display()} on {event.event_date:%d %b %Y}.'
    )
    return send_configured_notification(
        key='client_journey_event',
        recipient=event.client,
        actor=actor or event.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi journey event updated',
    )


def notify_journey_event_deleted(event, actor=None):
    title = 'Journey event removed'
    message = (
        f'Your {event.get_stage_display()} journey event dated {event.event_date:%d %b %Y} '
        'has been removed from your journey.'
    )
    return send_configured_notification(
        key='client_journey_event',
        recipient=event.client,
        actor=actor or event.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi journey event removed',
    )


def notify_referral_created(referral, actor=None):
    client_name = _display_name(referral.client)
    destination = referral.receiving_point_name or 'the receiving service point'
    title = 'Referral created'
    message = (
        f'A referral has been created for {destination}. '
        f'Reference: {referral.referral_code}. Status: {referral.get_confirmation_status_display()}.'
    )
    return send_configured_notification(
        key='client_referral',
        recipient=referral.client,
        actor=actor or referral.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi referral update',
        email_body=f'Hello {client_name},\n\n{message}\n\nPlease log in to MyThanzi to view the referral details.\n',
    )


def notify_referral_updated(referral, actor=None):
    destination = referral.receiving_point_name or 'the receiving service point'
    title = 'Referral updated'
    message = (
        f'Your referral to {destination} was updated. '
        f'Reference: {referral.referral_code}. Status: {referral.get_confirmation_status_display()}. '
        f'Outcome: {referral.get_initiation_outcome_display()}.'
    )
    return send_configured_notification(
        key='client_referral',
        recipient=referral.client,
        actor=actor or referral.confirmed_by or referral.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi referral updated',
    )


def notify_referral_deleted(referral, actor=None):
    destination = referral.receiving_point_name or 'the receiving service point'
    title = 'Referral removed'
    message = f'Your referral to {destination} with reference {referral.referral_code} has been removed.'
    return send_configured_notification(
        key='client_referral',
        recipient=referral.client,
        actor=actor or referral.recorded_by,
        title=title,
        message=message,
        email_subject='MyThanzi referral removed',
    )


def notify_follow_up_task_created(task, actor=None):
    client_name = _display_name(task.client)
    title = 'Follow-up task created'
    message = (
        f'A follow-up task was created for {task.get_reason_display().lower()} '
        f'and is due on {task.due_date:%d %b %Y}.'
    )
    client_notifications = send_configured_notification(
        key='client_follow_up_task',
        recipient=task.client,
        actor=actor or task.created_by,
        title=title,
        message=message,
        email_subject='MyThanzi follow-up update',
        email_body=f'Hello {client_name},\n\n{message}\n\nPlease log in to MyThanzi to view your care journey.\n',
    )

    staff_notifications = (None, None)
    if task.assigned_to_id and task.assigned_to_id != task.client_id:
        staff_title = 'Follow-up task assigned'
        staff_message = (
            f'You have been assigned a {task.get_priority_display().lower()} priority '
            f'{task.get_reason_display().lower()} task for {client_name}, due {task.due_date:%d %b %Y}.'
        )
        staff_notifications = send_configured_notification(
            key='staff_follow_up_task',
            recipient=task.assigned_to,
            actor=actor or task.created_by,
            title=staff_title,
            message=staff_message,
            email_subject='MyThanzi task assignment',
            email_body=f'Hello {_display_name(task.assigned_to)},\n\n{staff_message}\n\nPlease log in to MyThanzi to review the task.\n',
        )

    return client_notifications, staff_notifications


def notify_follow_up_task_updated(task, actor=None):
    title = 'Follow-up task updated'
    message = (
        f'Your follow-up task for {task.get_reason_display().lower()} was updated. '
        f'Status: {task.get_status_display()}. Due: {task.due_date:%d %b %Y}.'
    )
    client_notifications = send_configured_notification(
        key='client_follow_up_task',
        recipient=task.client,
        actor=actor or task.created_by,
        title=title,
        message=message,
        email_subject='MyThanzi follow-up task updated',
    )

    staff_notifications = (None, None)
    if task.assigned_to_id and task.assigned_to_id != task.client_id:
        staff_title = 'Assigned task updated'
        staff_message = (
            f'The {task.get_priority_display().lower()} priority {task.get_reason_display().lower()} '
            f'task for {_display_name(task.client)} was updated. Status: {task.get_status_display()}.'
        )
        staff_notifications = send_configured_notification(
            key='staff_follow_up_task',
            recipient=task.assigned_to,
            actor=actor or task.created_by,
            title=staff_title,
            message=staff_message,
            email_subject='MyThanzi assigned task updated',
        )

    return client_notifications, staff_notifications


def notify_follow_up_task_deleted(task, actor=None):
    title = 'Follow-up task removed'
    message = (
        f'Your follow-up task for {task.get_reason_display().lower()} due '
        f'{task.due_date:%d %b %Y} has been removed.'
    )
    client_notifications = send_configured_notification(
        key='client_follow_up_task',
        recipient=task.client,
        actor=actor or task.created_by,
        title=title,
        message=message,
        email_subject='MyThanzi follow-up task removed',
    )

    staff_notifications = (None, None)
    if task.assigned_to_id and task.assigned_to_id != task.client_id:
        staff_title = 'Assigned task removed'
        staff_message = (
            f'The {task.get_reason_display().lower()} task for {_display_name(task.client)} '
            f'due {task.due_date:%d %b %Y} has been removed.'
        )
        staff_notifications = send_configured_notification(
            key='staff_follow_up_task',
            recipient=task.assigned_to,
            actor=actor or task.created_by,
            title=staff_title,
            message=staff_message,
            email_subject='MyThanzi assigned task removed',
        )

    return client_notifications, staff_notifications
