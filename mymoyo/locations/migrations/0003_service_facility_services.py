from django.db import migrations, models


APPOINTMENT_SERVICES = [
    ('clinical_review', 'Clinical Review (Checkup)'),
    ('lab_collection', 'Lab Collection'),
    ('medication_refill', 'Medication Refill'),
    ('follow_up', 'Follow-up Visit'),
]


def seed_appointment_services(apps, schema_editor):
    Service = apps.get_model('locations', 'Service')
    Service.objects.bulk_create(
        [
            Service(code=code, name=name, description='', is_active=True)
            for code, name in APPOINTMENT_SERVICES
        ],
        ignore_conflicts=True,
    )


def unseed_appointment_services(apps, schema_editor):
    Service = apps.get_model('locations', 'Service')
    Service.objects.filter(code__in=[code for code, _name in APPOINTMENT_SERVICES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0002_facility_coordinates'),
    ]

    operations = [
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('code', models.SlugField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='facility',
            name='services',
            field=models.ManyToManyField(blank=True, related_name='facilities', to='locations.service'),
        ),
        migrations.RunPython(seed_appointment_services, unseed_appointment_services),
    ]
