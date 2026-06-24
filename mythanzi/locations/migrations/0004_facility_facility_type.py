from django.db import migrations, models


FACILITY_TYPE_MAP = [
    ('Central', 'Kapiri Mposhi', 'Kapiri Urban Health Centre', 'hub'),
    ('Central', 'Kapiri Mposhi', 'Tubombelepamo Wellness Center', 'spoke'),
    ('Copperbelt', 'Chingola', 'Chingola Correctional Health Post', 'hub'),
    ('Copperbelt', 'Chingola', 'Chingola Skills Training Centre (not activated)', 'spoke'),
    ('Copperbelt', 'Kitwe', 'Kitwe District Police Clinic', 'hub'),
    ('Copperbelt', 'Kitwe', 'PPAZ Kitwe', 'spoke'),
    ('Eastern', 'Chipata', 'Kapata Urban Health Centre', 'hub'),
    ('Eastern', 'Chipata', 'Chipata Day Youth Friendly Corner', 'spoke'),
    ('Lusaka', 'Chilanga', 'Chilanga Urban Health Centre', 'hub'),
    ('Lusaka', 'Chilanga', 'Mt. Makulu Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'Chawama Level One Hospital', 'hub'),
    ('Lusaka', 'Lusaka', 'Kuku Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'Matero Main Urban Health Centre', 'hub'),
    ('Lusaka', 'Lusaka', 'Chunga Sub Health Post', 'spoke'),
    ('Lusaka', 'Lusaka', 'UTH', 'hub'),
    ('Lusaka', 'Lusaka', 'PPAZ - UTH', 'spoke'),
    ('Muchinga', 'Nakonde', 'Nakonde Urban Health Centre', 'hub'),
    ('Northwestern', 'Solwezi', 'Solwezi Urban Health Centre', 'hub'),
    ('Northwestern', 'Solwezi', 'CHEK 1 Wellness Center', 'spoke'),
    ('Southern', 'Livingstone', 'Maramba Urban Health Centre', 'hub'),
    ('Southern', 'Livingstone', 'Mbita', 'spoke'),
    ('Southern', 'Mazabuka', 'Nakambala Urban Health Centre', 'hub'),
    ('Southern', 'Mazabuka', 'Nakambala Community Post', 'spoke'),
]


def map_facility_types(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, facility_name, facility_type in FACILITY_TYPE_MAP:
        Facility.objects.filter(
            name__iexact=facility_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
        ).update(facility_type=facility_type)


def unmap_facility_types(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, facility_name, facility_type in FACILITY_TYPE_MAP:
        Facility.objects.filter(
            name__iexact=facility_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
            facility_type=facility_type,
        ).update(facility_type='na')


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0003_service_facility_services'),
    ]

    operations = [
        migrations.AddField(
            model_name='facility',
            name='facility_type',
            field=models.CharField(
                choices=[('hub', 'Hub'), ('spoke', 'Spoke'), ('na', 'N/A')],
                default='na',
                max_length=10,
            ),
        ),
        migrations.RunPython(map_facility_types, unmap_facility_types),
    ]
