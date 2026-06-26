from django.db import migrations


HUB_SPOKE_SERVICE_CODES = [
    'clinical-follow-up',
    'clinical_review',
    'follow_up',
    'hiv-testing',
    'lab_collection',
    'medication_refill',
    'prep-len',
]


def apply_services_to_hub_spoke_facilities(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    Service = apps.get_model('locations', 'Service')
    service_ids = list(Service.objects.filter(code__in=HUB_SPOKE_SERVICE_CODES).values_list('pk', flat=True))
    if not service_ids:
        return

    through_model = Facility.services.through
    facility_ids = Facility.objects.filter(facility_type__in=['hub', 'spoke']).values_list('pk', flat=True)
    through_model.objects.bulk_create(
        [
            through_model(facility_id=facility_id, service_id=service_id)
            for facility_id in facility_ids
            for service_id in service_ids
        ],
        ignore_conflicts=True,
    )


def reverse_services_from_hub_spoke_facilities(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    Service = apps.get_model('locations', 'Service')
    service_ids = Service.objects.filter(code__in=HUB_SPOKE_SERVICE_CODES).values_list('pk', flat=True)
    facility_ids = Facility.objects.filter(facility_type__in=['hub', 'spoke']).values_list('pk', flat=True)
    Facility.services.through.objects.filter(
        facility_id__in=facility_ids,
        service_id__in=service_ids,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0007_apply_hub_spoke_alias_matches'),
    ]

    operations = [
        migrations.RunPython(apply_services_to_hub_spoke_facilities, reverse_services_from_hub_spoke_facilities),
    ]
