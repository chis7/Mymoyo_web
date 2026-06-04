from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .middleware import get_current_audit_user
from .models import AuditLog


AUDITED_APP_LABELS = {'auth', 'locations', 'users'}
EXCLUDED_MODELS = {
    ('auth', 'permission'),
    ('users', 'auditlog'),
}
SENSITIVE_FIELDS = {'password'}


def should_audit_model(model):
    meta = model._meta
    return meta.app_label in AUDITED_APP_LABELS and (meta.app_label, meta.model_name) not in EXCLUDED_MODELS


def serialize_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def serialize_instance(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        field_name = field.name
        if field_name in SENSITIVE_FIELDS:
            data[field_name] = '[redacted]'
        else:
            data[field_name] = serialize_value(getattr(instance, field.attname))
    return data


def sensitive_field_values(instance):
    return {
        field.name: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.name in SENSITIVE_FIELDS
    }


def changed_fields(before, after):
    changes = {}
    for key, after_value in after.items():
        before_value = before.get(key)
        if before_value != after_value:
            changes[key] = {
                'old': before_value,
                'new': after_value,
            }
    return changes


def create_audit_log(instance, action, changes=None, snapshot=None):
    AuditLog.objects.create(
        action=action,
        app_label=instance._meta.app_label,
        model_name=instance._meta.model_name,
        object_pk=str(instance.pk),
        object_repr=str(instance)[:255],
        actor=get_current_audit_user(),
        changes=changes or {},
        snapshot=snapshot or {},
    )


@receiver(pre_save, dispatch_uid='audit_capture_previous_state')
def capture_previous_state(sender, instance, **kwargs):
    if not should_audit_model(sender) or not instance.pk:
        return

    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._audit_previous_snapshot = {}
    else:
        instance._audit_previous_snapshot = serialize_instance(previous)
        instance._audit_previous_sensitive = sensitive_field_values(previous)


@receiver(post_save, dispatch_uid='audit_save')
def audit_save(sender, instance, created, **kwargs):
    if not should_audit_model(sender):
        return

    snapshot = serialize_instance(instance)
    if created:
        create_audit_log(instance, AuditLog.ACTION_CREATE, snapshot=snapshot)
        return

    before = getattr(instance, '_audit_previous_snapshot', {})
    changes = changed_fields(before, snapshot)
    previous_sensitive = getattr(instance, '_audit_previous_sensitive', {})
    for field_name, previous_value in previous_sensitive.items():
        if previous_value != sensitive_field_values(instance).get(field_name):
            changes[field_name] = {
                'old': '[redacted]',
                'new': '[redacted]',
            }
    if changes:
        create_audit_log(instance, AuditLog.ACTION_UPDATE, changes=changes, snapshot=snapshot)


@receiver(post_delete, dispatch_uid='audit_delete')
def audit_delete(sender, instance, **kwargs):
    if not should_audit_model(sender):
        return

    create_audit_log(
        instance,
        AuditLog.ACTION_DELETE,
        snapshot=serialize_instance(instance),
    )
