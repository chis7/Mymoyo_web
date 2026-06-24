import os

from django.contrib.auth.models import User
from django.core.management import BaseCommand, call_command
from django.db import transaction

from locations.models import District, Facility, Province, Service
from users.models import PersonIdentity, UserProfile


DEFAULT_SERVICES = [
    {
        'name': 'HIV Testing Services',
        'code': 'hiv-testing',
        'description': 'HIV testing, counseling, and linkage support.',
    },
    {
        'name': 'PrEP / LEN Services',
        'code': 'prep-len',
        'description': 'HIV prevention services including PrEP and long-acting options.',
    },
    {
        'name': 'Clinical Follow-up',
        'code': 'clinical-follow-up',
        'description': 'Continuity visits, side-effect review, and adherence support.',
    },
]

DEFAULT_FACILITIES = [
    {
        'province': 'Lusaka',
        'district': 'Lusaka',
        'name': 'University Teaching Hospital',
        'code': 'UTH',
        'level': 'Tertiary Hospital',
        'latitude': '-15.4326',
        'longitude': '28.3124',
    },
    {
        'province': 'Lusaka',
        'district': 'Lusaka',
        'name': 'Kanyama First Level Hospital',
        'code': 'KANYAMA-FLH',
        'level': 'First Level Hospital',
        'latitude': '-15.4036',
        'longitude': '28.2406',
    },
    {
        'province': 'Copperbelt',
        'district': 'Ndola',
        'name': 'Ndola Teaching Hospital',
        'code': 'NTH',
        'level': 'Teaching Hospital',
        'latitude': '-12.9587',
        'longitude': '28.6366',
    },
]


def env(name, default=''):
    return os.environ.get(name, default).strip()


class Command(BaseCommand):
    help = 'Seed a default admin account, services, and starter facilities.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-facilities',
            action='store_true',
            help='Create the admin user but skip facility/service seeding.',
        )

    def handle(self, *args, **options):
        if not options['skip_facilities']:
            self.seed_facilities()
        self.seed_admin()

    def seed_facilities(self):
        facility_file = env('INITIAL_FACILITIES_FILE')
        if facility_file:
            if os.path.exists(facility_file):
                self.stdout.write(f'Importing facilities from {facility_file}')
                call_command('import_locations', facility_file)
                self.seed_services(assign_to_existing=True)
                return

            self.stdout.write(self.style.WARNING(
                f'INITIAL_FACILITIES_FILE is set, but the file was not found: {facility_file}'
            ))

        self.seed_services(assign_to_existing=False)
        service_list = list(Service.objects.filter(code__in=[item['code'] for item in DEFAULT_SERVICES]))

        created_facilities = 0
        updated_facilities = 0
        with transaction.atomic():
            for item in DEFAULT_FACILITIES:
                province, _ = Province.objects.get_or_create(name=item['province'])
                district, _ = District.objects.get_or_create(name=item['district'], province=province)
                facility, created = Facility.objects.update_or_create(
                    name=item['name'],
                    district=district,
                    defaults={
                        'code': item['code'],
                        'level': item['level'],
                        'latitude': item['latitude'],
                        'longitude': item['longitude'],
                    },
                )
                facility.services.set(service_list)
                if created:
                    created_facilities += 1
                else:
                    updated_facilities += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded facilities. Created: {created_facilities}, updated: {updated_facilities}.'
        ))

    def seed_services(self, assign_to_existing):
        created_services = 0
        for item in DEFAULT_SERVICES:
            _, created = Service.objects.update_or_create(
                code=item['code'],
                defaults={
                    'name': item['name'],
                    'description': item['description'],
                    'is_active': True,
                },
            )
            if created:
                created_services += 1

        if assign_to_existing:
            services = Service.objects.filter(code__in=[item['code'] for item in DEFAULT_SERVICES])
            for facility in Facility.objects.all():
                facility.services.add(*services)

        self.stdout.write(self.style.SUCCESS(f'Seeded services. Created: {created_services}.'))

    def seed_admin(self):
        username = env('SEED_ADMIN_USERNAME') or env('DJANGO_SUPERUSER_USERNAME') or 'admin'
        email = env('SEED_ADMIN_EMAIL') or env('DJANGO_SUPERUSER_EMAIL') or 'admin@example.com'
        password = env('SEED_ADMIN_PASSWORD') or env('DJANGO_SUPERUSER_PASSWORD') or 'Admin123!'
        first_name = env('SEED_ADMIN_FIRST_NAME', 'System')
        last_name = env('SEED_ADMIN_LAST_NAME', 'Administrator')

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            },
        )

        changed_fields = []
        for field, value in {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        }.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed_fields.append(field)

        if created or env('SEED_ADMIN_RESET_PASSWORD', 'false').lower() in {'1', 'true', 'yes', 'on'}:
            user.set_password(password)
            changed_fields.append('password')

        if changed_fields:
            user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = 'admin'
        profile.is_active = True
        profile.is_phone_verified = True
        if not profile.person_identity_id:
            profile.person_identity = PersonIdentity.for_user_defaults(user)
        profile.save()

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} seeded admin user: {username}'))
