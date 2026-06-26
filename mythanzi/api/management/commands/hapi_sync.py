from django.core.management.base import BaseCommand, CommandError

from locations.models import District, Facility, Province
from users.models import Appointment, UserProfile
from api.fhir import logical_id, record_fhir_version, resource_type as fhir_resource_type
from api.hapi import (
    check_hapi_available,
    get_last_hapi_sync_error,
    hapi_sync_enabled,
    sync_fhir_version_to_hapi,
)
from api.models import FHIRResourceVersion


RESOURCE_SYNC_ORDER = {
    'Location': 10,
    'HealthcareService': 20,
    'Patient': 30,
    'Practitioner': 40,
    'Person': 50,
    'Appointment': 60,
    'Provenance': 70,
}


class Command(BaseCommand):
    help = 'Sync recorded MyThanzi FHIR resource versions to the HAPI FHIR server.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all-versions',
            action='store_true',
            help='Sync every recorded version. By default, only latest versions are synced.',
        )
        parser.add_argument(
            '--resource-type',
            help='Only sync one FHIR resource type, e.g. Patient, Location, Appointment.',
        )
        parser.add_argument(
            '--include-provenance',
            action='store_true',
            help='Also sync audit logs as Provenance. Skipped by default because audit history can be very large.',
        )

    def handle(self, *args, **options):
        if not hapi_sync_enabled():
            self.stderr.write(self.style.WARNING('HAPI sync is disabled or HAPI_FHIR_BASE_URL is empty.'))
            return
        available, detail = check_hapi_available()
        if not available:
            raise CommandError(f'HAPI is not reachable. Start hapi-db and hapi-fhir first. Detail: {detail}')

        resource_type = options.get('resource_type')

        if not options['all_versions'] and not resource_type:
            self._ensure_location_dependencies()
            self._ensure_appointment_dependencies()
            self._retire_stale_user_profile_resources()

        queryset = FHIRResourceVersion.objects.order_by('resource_type', 'logical_id', 'version_id')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        elif not options['include_provenance']:
            queryset = queryset.exclude(resource_type='Provenance')

        if not options['all_versions']:
            latest_ids = {}
            for version in queryset.order_by('resource_type', 'logical_id', '-version_id'):
                key = (version.resource_type, version.logical_id)
                if key not in latest_ids:
                    latest_ids[key] = version.pk
            queryset = FHIRResourceVersion.objects.filter(pk__in=latest_ids.values())

        synced_count = 0
        failed_count = 0
        failure_examples = []
        failure_by_type = {}
        versions = sorted(
            queryset,
            key=lambda version: (
                RESOURCE_SYNC_ORDER.get(version.resource_type, 999),
                version.resource_type,
                version.logical_id,
                version.version_id,
            ),
        )
        for version in versions:
            result = sync_fhir_version_to_hapi(version)
            if result is True:
                synced_count += 1
            elif result is None:
                raise CommandError(
                    'HAPI became unreachable during sync. Restart hapi-fhir and rerun this command.'
                )
            else:
                failed_count += 1
                failure_by_type[version.resource_type] = failure_by_type.get(version.resource_type, 0) + 1
                if len(failure_examples) < 5:
                    failure_examples.append((
                        version.resource_type,
                        version.logical_id,
                        version.version_id,
                        get_last_hapi_sync_error(),
                    ))

        self.stdout.write(self.style.SUCCESS(f'Synced {synced_count} FHIR version(s) to HAPI.'))
        if failed_count:
            self.stderr.write(self.style.WARNING(f'{failed_count} FHIR version(s) could not be synced.'))
            summary = ', '.join(f'{key}: {value}' for key, value in sorted(failure_by_type.items()))
            self.stderr.write(self.style.WARNING(f'Failures by resource type: {summary}'))
            self.stderr.write(self.style.WARNING('First failures:'))
            for resource_type, logical_id, version_id, detail in failure_examples:
                self.stderr.write(f'- {resource_type}/{logical_id} v{version_id}: {detail[:1000]}')

    def _ensure_location_dependencies(self):
        models = (Province, District, Facility)
        for model in models:
            queryset = model.objects.all()
            if model is District:
                queryset = queryset.select_related('province')
            if model is Facility:
                queryset = queryset.select_related('district__province')
            for instance in queryset.iterator(chunk_size=500):
                latest = (
                    FHIRResourceVersion.objects
                    .filter(resource_type='Location', logical_id=f'{instance._meta.model_name}-{instance.pk}')
                    .order_by('-version_id')
                    .first()
                )
                if latest:
                    continue
                record_fhir_version(instance, FHIRResourceVersion.ACTION_CREATE, sync_to_hapi=False)

    def _ensure_appointment_dependencies(self):
        appointments = Appointment.objects.select_related(
            'beneficiary__profile',
            'created_by__profile',
            'province',
            'district',
            'facility',
        )
        for appointment in appointments.iterator(chunk_size=500):
            self._ensure_current_dependency_version(appointment.province)
            self._ensure_current_dependency_version(appointment.district)
            self._ensure_current_dependency_version(appointment.facility)
            if hasattr(appointment.beneficiary, 'profile'):
                self._ensure_current_dependency_version(appointment.beneficiary.profile)
            if appointment.created_by_id and hasattr(appointment.created_by, 'profile'):
                self._ensure_current_dependency_version(appointment.created_by.profile)

    def _ensure_current_dependency_version(self, instance):
        if not instance:
            return
        latest = (
            FHIRResourceVersion.objects
            .filter(
                resource_type=fhir_resource_type(instance),
                logical_id=logical_id(instance),
            )
            .order_by('-version_id')
            .first()
        )
        if latest and latest.action != FHIRResourceVersion.ACTION_DELETE:
            return
        action = FHIRResourceVersion.ACTION_UPDATE if latest else FHIRResourceVersion.ACTION_CREATE
        record_fhir_version(instance, action, sync_to_hapi=False)

    def _retire_stale_user_profile_resources(self):
        active_profile_ids = {f'user-{user_id}' for user_id in UserProfile.objects.values_list('user_id', flat=True)}
        for profile in UserProfile.objects.select_related('user').iterator(chunk_size=500):
            current_type = fhir_resource_type(profile)
            stale_type = 'Practitioner' if current_type == 'Patient' else 'Patient'
            stale_latest = (
                FHIRResourceVersion.objects
                .filter(resource_type=stale_type, logical_id=logical_id(profile))
                .order_by('-version_id')
                .first()
            )
            if not stale_latest or stale_latest.action == FHIRResourceVersion.ACTION_DELETE:
                continue
            version_id = stale_latest.version_id + 1
            FHIRResourceVersion.objects.create(
                resource_type=stale_type,
                logical_id=logical_id(profile),
                version_id=version_id,
                action=FHIRResourceVersion.ACTION_DELETE,
                source_app=profile._meta.app_label,
                source_model=profile._meta.model_name,
                source_pk=str(profile.pk),
                resource={
                    'resourceType': stale_type,
                    'id': logical_id(profile),
                    'meta': {'versionId': str(version_id)},
                },
            )

        for resource_type in ('Patient', 'Practitioner'):
            latest_ids = {}
            for version in FHIRResourceVersion.objects.filter(resource_type=resource_type).order_by('logical_id', '-version_id'):
                latest_ids.setdefault(version.logical_id, version.pk)
            orphaned_versions = (
                FHIRResourceVersion.objects
                .filter(pk__in=latest_ids.values())
                .exclude(action=FHIRResourceVersion.ACTION_DELETE)
                .exclude(logical_id__in=active_profile_ids)
            )
            for latest in orphaned_versions:
                version_id = latest.version_id + 1
                FHIRResourceVersion.objects.create(
                    resource_type=latest.resource_type,
                    logical_id=latest.logical_id,
                    version_id=version_id,
                    action=FHIRResourceVersion.ACTION_DELETE,
                    source_app=latest.source_app,
                    source_model=latest.source_model,
                    source_pk=latest.source_pk,
                    resource={
                        'resourceType': latest.resource_type,
                        'id': latest.logical_id,
                        'meta': {'versionId': str(version_id)},
                    },
                )
