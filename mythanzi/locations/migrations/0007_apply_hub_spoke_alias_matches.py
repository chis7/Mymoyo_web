from django.db import migrations


ALIAS_ROWS = [
    ('Copperbelt', 'Kitwe', 'Kitwe District Police Clinic', 'Kitwe District Police Health Centre', None, 'hub'),
    ('Lusaka', 'Lusaka', 'Chawama Level One Hospital', 'Chawama First Level  Hospital', None, 'hub'),
    ('Lusaka', 'Lusaka', 'UTH', 'University Teaching Hospital', None, 'hub'),
    ('Lusaka', 'Lusaka', 'Matero Main Urban Health Centre', 'Chunga Sub-Centre Health Post', 'Matero Main Urban Health Centre', 'spoke'),
    ('Lusaka', 'Lusaka', 'UTH', 'Planned Parenthood Association (PPAZ) Clinic- Lusaka', 'University Teaching Hospital', 'spoke'),
    ('Southern', 'Livingstone', 'Maramba Urban Health Centre', 'Mbita Health Post', 'Maramba Urban Health Centre', 'spoke'),
]


def find_facility(Facility, province_name, district_name, facility_name):
    return Facility.objects.filter(
        name__iexact=facility_name,
        district__name__iexact=district_name,
        district__province__name__iexact=province_name,
    ).first()


def apply_alias_matches(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, _source_name, existing_name, hub_existing_name, facility_type in ALIAS_ROWS:
        facility = find_facility(Facility, province_name, district_name, existing_name)
        if not facility:
            continue
        facility.facility_type = facility_type
        update_fields = ['facility_type']
        if facility_type == 'spoke' and hub_existing_name:
            hub = find_facility(Facility, province_name, district_name, hub_existing_name)
            if hub:
                hub.facility_type = 'hub'
                hub.save(update_fields=['facility_type'])
                facility.hub_id = hub.pk
                update_fields.append('hub')
        facility.save(update_fields=update_fields)

    kuku = find_facility(Facility, 'Lusaka', 'Lusaka', 'Kuku Health Post')
    chawama = find_facility(Facility, 'Lusaka', 'Lusaka', 'Chawama First Level  Hospital')
    if kuku and chawama:
        chawama.facility_type = 'hub'
        chawama.save(update_fields=['facility_type'])
        kuku.facility_type = 'spoke'
        kuku.hub_id = chawama.pk
        kuku.save(update_fields=['facility_type', 'hub'])


def reverse_alias_matches(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, _source_name, existing_name, _hub_existing_name, _facility_type in ALIAS_ROWS:
        facility = find_facility(Facility, province_name, district_name, existing_name)
        if facility:
            facility.facility_type = 'na'
            facility.hub_id = None
            facility.save(update_fields=['facility_type', 'hub'])

    kuku = find_facility(Facility, 'Lusaka', 'Lusaka', 'Kuku Health Post')
    if kuku:
        kuku.hub_id = None
        kuku.save(update_fields=['hub'])


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0006_reapply_facility_hub_spoke_mapping'),
    ]

    operations = [
        migrations.RunPython(apply_alias_matches, reverse_alias_matches),
    ]
