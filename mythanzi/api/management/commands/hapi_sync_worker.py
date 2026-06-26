import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Continuously backfill and sync MyThanzi FHIR resources to HAPI.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=900,
            help='Seconds to wait between full sync passes. Default: 900.',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run one backfill and full sync pass, then exit.',
        )
        parser.add_argument(
            '--skip-provenance',
            action='store_true',
            help='Skip audit Provenance resources during catch-up sync.',
        )

    def handle(self, *args, **options):
        interval = max(options['interval'], 60)
        while True:
            started_at = time.monotonic()
            self.stdout.write('Starting automated HAPI FHIR backfill and sync pass.')
            call_command('fhir_backfill')
            call_command('hapi_sync', include_provenance=not options['skip_provenance'])
            elapsed = round(time.monotonic() - started_at, 1)
            self.stdout.write(self.style.SUCCESS(f'Automated HAPI FHIR sync pass completed in {elapsed}s.'))

            if options['once']:
                return
            time.sleep(interval)
