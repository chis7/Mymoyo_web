from django.db import migrations, models
import django.db.models.deletion


HUB_SPOKE_MAP = [
    ('Central', 'Kapiri Mposhi', 'Kapiri Urban Health Centre', 'Tubombelepamo Wellness Center'),
    ('Copperbelt', 'Chingola', 'Chingola Correctional Health Post', 'Chingola Skills Training Centre (not activated)'),
    ('Copperbelt', 'Kitwe', 'Kitwe District Police Clinic', 'PPAZ Kitwe'),
    ('Eastern', 'Chipata', 'Kapata Urban Health Centre', 'Chipata Day Youth Friendly Corner'),
    ('Lusaka', 'Chilanga', 'Chilanga Urban Health Centre', 'Mt. Makulu Health Post'),
    ('Lusaka', 'Lusaka', 'Chawama Level One Hospital', 'Kuku Health Post'),
    ('Lusaka', 'Lusaka', 'Matero Main Urban Health Centre', 'Chunga Sub Health Post'),
    ('Lusaka', 'Lusaka', 'UTH', 'PPAZ - UTH'),
    ('Northwestern', 'Solwezi', 'Solwezi Urban Health Centre', 'CHEK 1 Wellness Center'),
    ('Southern', 'Livingstone', 'Maramba Urban Health Centre', 'Mbita'),
    ('Southern', 'Mazabuka', 'Nakambala Urban Health Centre', 'Nakambala Community Post'),
]


def map_hub_spokes(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, hub_name, spoke_name in HUB_SPOKE_MAP:
        hub = Facility.objects.filter(
            name__iexact=hub_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
        ).first()
        if not hub:
            continue
        Facility.objects.filter(
            name__iexact=spoke_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
        ).update(hub_id=hub.pk, facility_type='spoke')


def unmap_hub_spokes(apps, schema_editor):
    Facility = apps.get_model('locations', 'Facility')
    for province_name, district_name, hub_name, spoke_name in HUB_SPOKE_MAP:
        hub = Facility.objects.filter(
            name__iexact=hub_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
        ).first()
        if not hub:
            continue
        Facility.objects.filter(
            name__iexact=spoke_name,
            district__name__iexact=district_name,
            district__province__name__iexact=province_name,
            hub_id=hub.pk,
        ).update(hub_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0004_facility_facility_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='facility',
            name='hub',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'facility_type': 'hub'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='spokes',
                to='locations.facility',
            ),
        ),
        migrations.RunPython(map_hub_spokes, unmap_hub_spokes),
    ]
