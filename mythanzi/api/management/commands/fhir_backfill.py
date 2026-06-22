from django.core.management.base import BaseCommand

from locations.models import District, Facility, Province, Service
from users.models import Appointment, AuditLog, PersonIdentity, UserProfile

from api.fhir import logical_id, record_fhir_version, resource_type
from api.models import FHIRResourceVersion


class Command(BaseCommand):
    help = 'Create initial FHIR resource versions for existing MyThanzi records.'

    def handle(self, *args, **options):
        created_count = 0
        models = [Province, District, Service, Facility, PersonIdentity, UserProfile, Appointment, AuditLog]

        for model in models:
            queryset = model.objects.all()
            if model is District:
                queryset = queryset.select_related('province')
            if model is Facility:
                queryset = queryset.select_related('district__province')
            if model is PersonIdentity:
                queryset = queryset.prefetch_related('profiles__user')
            if model is UserProfile:
                queryset = queryset.select_related('user', 'person_identity', 'facility')
            if model is Appointment:
                queryset = queryset.select_related(
                    'beneficiary__profile',
                    'created_by__profile',
                    'province',
                    'district',
                    'facility',
                )
            if model is AuditLog:
                queryset = queryset.select_related('actor__profile')

            for instance in queryset.iterator(chunk_size=500):
                if FHIRResourceVersion.objects.filter(
                    resource_type=resource_type(instance),
                    logical_id=logical_id(instance),
                ).exists():
                    continue
                record_fhir_version(instance, FHIRResourceVersion.ACTION_CREATE, sync_to_hapi=False)
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Backfilled {created_count} FHIR resource version(s).'))
        self.stdout.write('Run `python manage.py hapi_sync` to push these versions to HAPI in dependency order.')
