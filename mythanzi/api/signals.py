from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from locations.models import District, Facility, Province, Service
from users.models import Appointment, AuditLog, PersonIdentity, UserProfile

from .fhir import record_fhir_version
from .models import FHIRResourceVersion


TRACKED_SENDERS = (Province, District, Service, Facility, PersonIdentity, UserProfile, Appointment, AuditLog)


def _record_after_commit(instance, action):
    if isinstance(instance, FHIRResourceVersion):
        return

    def callback():
        try:
            record_fhir_version(instance, action)
        except Exception:
            # FHIR history should never make the operational save fail.
            pass

    transaction.on_commit(callback)


for tracked_sender in TRACKED_SENDERS:
    post_save.connect(
        lambda sender, instance, created, **kwargs: _record_after_commit(
            instance,
            FHIRResourceVersion.ACTION_CREATE if created else FHIRResourceVersion.ACTION_UPDATE,
        ),
        sender=tracked_sender,
        weak=False,
        dispatch_uid=f'fhir-post-save-{tracked_sender._meta.label_lower}',
    )
    post_delete.connect(
        lambda sender, instance, **kwargs: _record_after_commit(instance, FHIRResourceVersion.ACTION_DELETE),
        sender=tracked_sender,
        weak=False,
        dispatch_uid=f'fhir-post-delete-{tracked_sender._meta.label_lower}',
    )
