import re

from django.db import migrations


FACILITY_ROWS = [
    ('Central', 'Kapiri Mposhi', 'Kapiri Urban Health Centre', None, 'Kapiri Urban Health Centre', 'hub'),
    ('Central', 'Kapiri Mposhi', 'Kapiri Urban Health Centre', 'Tubombelepamo Wellness Center', 'Tubombelepamo Wellness Center', 'spoke'),
    ('Copperbelt', 'Chingola', 'Chingola Correctional Health Post', None, 'Chingola Correctional Health Post', 'hub'),
    ('Copperbelt', 'Chingola', 'Chingola Correctional Health Post', 'Chingola Skills Training Centre (not activated)', 'Chingola Skills Training Centre (not activated)', 'spoke'),
    ('Copperbelt', 'Kitwe', 'Kitwe District Police Clinic', None, 'Kitwe District Police Clinic', 'hub'),
    ('Copperbelt', 'Kitwe', 'Kitwe District Police Clinic', 'PPAZ Kitwe', 'PPAZ Kitwe', 'spoke'),
    ('Eastern', 'Chipata', 'Kapata Urban Health Centre', None, 'Kapata Urban Health Centre', 'hub'),
    ('Eastern', 'Chipata', 'Kapata Urban Health Centre', 'Chipata Day Youth Friendly Corner', 'Chipata Day Youth Friendly Corner', 'spoke'),
    ('Lusaka', 'Chilanga', 'Chilanga Urban Health Centre', None, 'Chilanga Urban Health Centre', 'hub'),
    ('Lusaka', 'Chilanga', 'Chilanga Urban Health Centre', 'Mt. Makulu Health Post', 'Mt. Makulu Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'Chawama Level One Hospital', None, 'Chawama Level One Hospital', 'hub'),
    ('Lusaka', 'Lusaka', 'Chawama Level One Hospital', 'Kuku Health Post', 'Kuku Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'Matero Main Urban Health Centre', None, 'Matero Main Urban Health Centre', 'hub'),
    ('Lusaka', 'Lusaka', 'Matero Main Urban Health Centre', 'Chunga Sub Health Post', 'Chunga Sub Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'UTH', None, 'UTH', 'hub'),
    ('Lusaka', 'Lusaka', 'UTH', 'PPAZ - UTH', 'PPAZ - UTH', 'spoke'),
    ('Muchinga', 'Nakonde', 'Nakonde Urban Health Centre', None, 'Nakonde Urban Health Centre', 'hub'),
    ('Northwestern', 'Solwezi', 'Solwezi Urban Health Centre', None, 'Solwezi Urban Health Centre', 'hub'),
    ('Northwestern', 'Solwezi', 'Solwezi Urban Health Centre', 'CHEK 1 Wellness Center', 'CHEK 1 Wellness Center', 'spoke'),
    ('Southern', 'Livingstone', 'Maramba Urban Health Centre', None, 'Maramba Urban Health Centre', 'hub'),
    ('Southern', 'Livingstone', 'Maramba Urban Health Centre', 'Mbita', 'Mbita', 'spoke'),
    ('Southern', 'Mazabuka', 'Nakambala Urban Health Centre', None, 'Nakambala Urban Health Centre', 'hub'),
    ('Southern', 'Mazabuka', 'Nakambala Urban Health Centre', 'Nakambala Community Post', 'Nakambala Community Post', 'spoke'),
]


def normalize(value):
    value = str(value or '').lower().replace('centre', 'center')
    return re.sub(r'[^a-z0-9]+', '', value)


def build_facility_indexes(Facility):
    by_location_name = {}
    by_province_name = {}
    facilities = Facility.objects.select_related('district__province')
    for facility in facilities:
        province = normalize(facility.district.province.name)
        district = normalize(facility.district.name)
        name = normalize(facility.name)
        by_location_name.setdefault((province, district, name), []).append(facility)
        by_province_name.setdefault((province, name), []).append(facility)
    return by_location_name, by_province_name


def find_facility(indexes, province_name, district_name, facility_name):
    by_location_name, by_province_name = indexes
    province = normalize(province_name)
    district = normalize(district_name)
    name = normalize(facility_name)
    matches = by_location_name.get((province, district, name), [])
    if len(matches) == 1:
        return matches[0]
    matches = by_province_name.get((province, name), [])
    if len(matches) == 1:
        return matches[0]
    return None


def reapply_facility_mapping(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    Facility.objects.filter(facility_type__isnull=True).update(facility_type='na')
    indexes = build_facility_indexes(Facility)

    for province_name, district_name, _hub_name, _spoke_name, facility_name, facility_type in FACILITY_ROWS:
        facility = find_facility(indexes, province_name, district_name, facility_name)
        if facility:
            facility.facility_type = facility_type
            facility.save(update_fields=['facility_type'])

    indexes = build_facility_indexes(Facility)
    for province_name, district_name, hub_name, spoke_name, _facility_name, facility_type in FACILITY_ROWS:
        if facility_type != 'spoke' or not spoke_name:
            continue
        spoke = find_facility(indexes, province_name, district_name, spoke_name)
        hub = find_facility(indexes, province_name, district_name, hub_name)
        if spoke and hub:
            spoke.facility_type = 'spoke'
            spoke.hub_id = hub.pk
            spoke.save(update_fields=['facility_type', 'hub'])


def reverse_facility_mapping(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    indexes = build_facility_indexes(Facility)
    for province_name, district_name, _hub_name, _spoke_name, facility_name, _facility_type in FACILITY_ROWS:
        facility = find_facility(indexes, province_name, district_name, facility_name)
        if facility:
            facility.facility_type = 'na'
            facility.hub_id = None
            facility.save(update_fields=['facility_type', 'hub'])


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0005_facility_hub'),
    ]

    operations = [
        migrations.RunPython(reapply_facility_mapping, reverse_facility_mapping),
    ]
