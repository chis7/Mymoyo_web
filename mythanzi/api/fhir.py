from datetime import datetime

from django.contrib.auth.models import User
from django.utils import timezone

from locations.models import District, Facility, Province, Service
from users.models import Appointment, AuditLog, PersonIdentity, UserProfile

from .models import FHIRResourceVersion
from .hapi import sync_fhir_version_to_hapi


TRACKED_MODELS = (Province, District, Service, Facility, PersonIdentity, UserProfile, Appointment, AuditLog)


def _instant(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.isoformat()


def _date(value):
    return value.isoformat() if value else None


def _reference(resource_type, logical_id, display=None):
    data = {'reference': f'{resource_type}/{logical_id}'}
    if display:
        data['display'] = str(display)
    return data


def user_resource_type(profile):
    return 'Patient' if profile.role == 'client' else 'Practitioner'


def logical_id(instance):
    if isinstance(instance, Province):
        return f'province-{instance.pk}'
    if isinstance(instance, District):
        return f'district-{instance.pk}'
    if isinstance(instance, Facility):
        return f'facility-{instance.pk}'
    if isinstance(instance, Service):
        return f'service-{instance.pk}'
    if isinstance(instance, PersonIdentity):
        return f'person-{instance.pk}'
    if isinstance(instance, UserProfile):
        return f'user-{instance.user_id}'
    if isinstance(instance, Appointment):
        return f'appointment-{instance.pk}'
    if isinstance(instance, AuditLog):
        return f'audit-{instance.pk}'
    return str(instance.pk)


def resource_type(instance):
    if isinstance(instance, (Province, District, Facility)):
        return 'Location'
    if isinstance(instance, Service):
        return 'HealthcareService'
    if isinstance(instance, PersonIdentity):
        return 'Person'
    if isinstance(instance, UserProfile):
        return user_resource_type(instance)
    if isinstance(instance, Appointment):
        return 'Appointment'
    if isinstance(instance, AuditLog):
        return 'Provenance'
    raise TypeError(f'No FHIR mapping is registered for {type(instance).__name__}.')


def _base_resource(instance):
    return {
        'resourceType': resource_type(instance),
        'id': logical_id(instance),
        'meta': {
            'profile': ['https://mythanzi.local/fhir/StructureDefinition/mythanzi-resource'],
        },
    }


def _location_for_province(province):
    resource = _base_resource(province)
    resource.update({
        'status': 'active',
        'name': province.name,
        'mode': 'instance',
        'type': [{
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/v3-RoleCode',
                'code': 'JURIS',
                'display': 'Jurisdiction',
            }],
            'text': 'Province',
        }],
    })
    return resource


def _location_for_district(district):
    resource = _base_resource(district)
    resource.update({
        'status': 'active',
        'name': district.name,
        'mode': 'instance',
        'partOf': _reference('Location', logical_id(district.province), district.province.name),
        'type': [{'text': 'District'}],
    })
    return resource


def _location_for_facility(facility):
    resource = _base_resource(facility)
    resource.update({
        'status': 'active',
        'name': facility.name,
        'mode': 'instance',
        'partOf': _reference('Location', logical_id(facility.district), facility.district.name),
        'type': [{'text': facility.level or 'Facility'}],
    })
    if facility.code:
        resource['identifier'] = [{
            'system': 'https://mythanzi.local/fhir/NamingSystem/facility-code',
            'value': facility.code,
        }]
    if facility.latitude is not None and facility.longitude is not None:
        resource['position'] = {
            'longitude': float(facility.longitude),
            'latitude': float(facility.latitude),
        }
    return resource


def _healthcare_service(service):
    resource = _base_resource(service)
    resource.update({
        'active': service.is_active,
        'name': service.name,
        'identifier': [{
            'system': 'https://mythanzi.local/fhir/NamingSystem/service-code',
            'value': service.code,
        }],
    })
    if service.description:
        resource['comment'] = service.description
    return resource


def _human_name(user):
    name = {
        'use': 'official',
        'text': user.get_full_name().strip() or user.username,
    }
    if user.first_name:
        name['given'] = [user.first_name]
    if user.last_name:
        name['family'] = user.last_name
    return [name]


def _identity_resource(identity):
    resource = _base_resource(identity)
    resource.update({
        'active': True,
        'name': [{'use': 'official', 'text': identity.full_name}],
    })
    if identity.phone:
        resource['telecom'] = [{'system': 'phone', 'value': identity.phone}]
    if identity.date_of_birth:
        resource['birthDate'] = _date(identity.date_of_birth)
    links = []
    for profile in identity.profiles.select_related('user'):
        links.append({
            'target': _reference(user_resource_type(profile), logical_id(profile), profile.user.get_full_name() or profile.user.username),
        })
    if links:
        resource['link'] = links
    return resource


def _person_resource(profile):
    user = profile.user
    resource = _base_resource(profile)
    resource.update({
        'active': bool(profile.is_active and user.is_active),
        'identifier': [{
            'system': 'https://mythanzi.local/fhir/NamingSystem/client-reference',
            'value': profile.reference_number,
        }],
        'name': _human_name(user),
    })
    telecom = []
    if profile.phone:
        telecom.append({'system': 'phone', 'value': profile.phone})
    if user.email:
        telecom.append({'system': 'email', 'value': user.email})
    if telecom:
        resource['telecom'] = telecom
    if profile.date_of_birth:
        resource['birthDate'] = _date(profile.date_of_birth)
    if profile.person_identity_id:
        resource.setdefault('extension', []).append({
            'url': 'https://mythanzi.local/fhir/StructureDefinition/person-identity',
            'valueReference': _reference('Person', logical_id(profile.person_identity), profile.person_identity.full_name),
        })
    if resource['resourceType'] == 'Practitioner':
        resource['qualification'] = [{'code': {'text': profile.get_role_display()}}]
        if profile.facility_id:
            resource.setdefault('extension', []).append({
                'url': 'https://mythanzi.local/fhir/StructureDefinition/worker-facility',
                'valueReference': _reference('Location', logical_id(profile.facility), profile.facility.name),
            })
    return resource


def _appointment_resource(appointment):
    resource = _base_resource(appointment)
    start = timezone.make_aware(datetime.combine(appointment.appointment_date, appointment.appointment_time), timezone.get_current_timezone())
    beneficiary_profile = appointment.beneficiary.profile
    participant = [{
        'actor': _reference(user_resource_type(beneficiary_profile), logical_id(beneficiary_profile), appointment.beneficiary.get_full_name() or appointment.beneficiary.username),
        'status': 'accepted',
    }]
    if appointment.created_by_id and hasattr(appointment.created_by, 'profile'):
        creator_profile = appointment.created_by.profile
        participant.append({
            'actor': _reference(user_resource_type(creator_profile), logical_id(creator_profile), appointment.created_by.get_full_name() or appointment.created_by.username),
            'status': 'accepted',
        })
    resource.update({
        'status': {
            'upcoming': 'booked',
            'completed': 'fulfilled',
            'missed': 'noshow',
        }.get(appointment.status, 'booked'),
        'serviceType': [{'concept': {'text': appointment.get_visit_purpose_display()}}],
        'start': _instant(start),
        'created': _instant(appointment.created_at),
        'participant': participant,
        'supportingInformation': [
            _reference('Location', logical_id(appointment.province), appointment.province.name),
            _reference('Location', logical_id(appointment.district), appointment.district.name),
            _reference('Location', logical_id(appointment.facility), appointment.facility.name),
        ],
    })
    if appointment.notes:
        resource['comment'] = appointment.notes
    return resource


def _provenance_resource(audit_log):
    resource = _base_resource(audit_log)
    resource.update({
        'recorded': _instant(audit_log.created_at),
        'activity': {'text': audit_log.get_action_display()},
        'target': [{
            'identifier': {
                'system': f'https://mythanzi.local/source/{audit_log.app_label}/{audit_log.model_name}',
                'value': audit_log.object_pk,
            },
            'display': audit_log.object_repr,
        }],
        'entity': [{
            'role': 'source',
            'what': {
                'identifier': {
                    'system': f'https://mythanzi.local/source/{audit_log.app_label}/{audit_log.model_name}',
                    'value': audit_log.object_pk,
                }
            },
        }],
    })
    if audit_log.actor_id:
        try:
            profile = audit_log.actor.profile
            resource['agent'] = [{
                'who': _reference(user_resource_type(profile), logical_id(profile), audit_log.actor.get_full_name() or audit_log.actor.username),
            }]
        except UserProfile.DoesNotExist:
            pass
    return resource


def to_fhir_resource(instance):
    if isinstance(instance, Province):
        return _location_for_province(instance)
    if isinstance(instance, District):
        return _location_for_district(instance)
    if isinstance(instance, Facility):
        return _location_for_facility(instance)
    if isinstance(instance, Service):
        return _healthcare_service(instance)
    if isinstance(instance, PersonIdentity):
        return _identity_resource(instance)
    if isinstance(instance, UserProfile):
        return _person_resource(instance)
    if isinstance(instance, Appointment):
        return _appointment_resource(instance)
    if isinstance(instance, AuditLog):
        return _provenance_resource(instance)
    raise TypeError(f'No FHIR mapping is registered for {type(instance).__name__}.')


def record_fhir_version(instance, action, sync_to_hapi=True):
    if not isinstance(instance, TRACKED_MODELS):
        return None

    resource = to_fhir_resource(instance)
    type_name = resource['resourceType']
    id_value = resource['id']
    latest = (
        FHIRResourceVersion.objects
        .filter(resource_type=type_name, logical_id=id_value)
        .order_by('-version_id')
        .first()
    )
    version_id = (latest.version_id if latest else 0) + 1
    resource['meta']['versionId'] = str(version_id)
    resource['meta']['lastUpdated'] = timezone.now().isoformat()

    version = FHIRResourceVersion.objects.create(
        resource_type=type_name,
        logical_id=id_value,
        version_id=version_id,
        action=action,
        source_app=instance._meta.app_label,
        source_model=instance._meta.model_name,
        source_pk=str(instance.pk),
        resource=resource,
    )
    if sync_to_hapi:
        sync_fhir_version_to_hapi(version)
    return version


def latest_resources(resource_type_name=None):
    queryset = FHIRResourceVersion.objects.all()
    if resource_type_name:
        queryset = queryset.filter(resource_type=resource_type_name)
    latest_ids = {}
    for version in queryset.order_by('resource_type', 'logical_id', '-version_id'):
        key = (version.resource_type, version.logical_id)
        if key not in latest_ids:
            latest_ids[key] = version.pk
    return FHIRResourceVersion.objects.filter(pk__in=latest_ids.values()).order_by('resource_type', 'logical_id')
