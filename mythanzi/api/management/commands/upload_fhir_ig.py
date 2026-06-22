import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Upload a FHIR IG transaction Bundle to the configured HAPI FHIR server.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default='fhir_ig/mythanzi-ig-bundle.json',
            help='Path to a FHIR transaction Bundle JSON file, relative to BASE_DIR unless absolute.',
        )

    def handle(self, *args, **options):
        base_url = getattr(settings, 'HAPI_FHIR_BASE_URL', '').rstrip('/')
        if not base_url:
            raise CommandError('HAPI_FHIR_BASE_URL is empty.')

        bundle_path = Path(options['file'])
        if not bundle_path.is_absolute():
            bundle_path = Path(settings.BASE_DIR) / bundle_path

        if not bundle_path.exists():
            raise CommandError(f'FHIR IG bundle file was not found: {bundle_path}')

        try:
            with bundle_path.open(encoding='utf-8') as handle:
                bundle = json.load(handle)
        except json.JSONDecodeError as exc:
            raise CommandError(f'FHIR IG bundle is not valid JSON: {exc}') from exc

        if bundle.get('resourceType') != 'Bundle' or bundle.get('type') != 'transaction':
            raise CommandError('FHIR IG upload file must be a Bundle with type "transaction".')

        payload = json.dumps(bundle).encode('utf-8')
        request = Request(
            base_url,
            data=payload,
            headers={
                'Accept': 'application/fhir+json',
                'Content-Type': 'application/fhir+json',
            },
            method='POST',
        )

        try:
            with urlopen(request, timeout=settings.HAPI_FHIR_TIMEOUT_SECONDS) as response:
                body = response.read().decode('utf-8', errors='replace')
        except HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise CommandError(f'HAPI rejected the IG bundle with HTTP {exc.code}: {detail}') from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CommandError(f'Could not reach HAPI at {base_url}: {exc}') from exc

        response_bundle = json.loads(body) if body else {}
        entry_count = len(response_bundle.get('entry', []))
        self.stdout.write(self.style.SUCCESS(
            f'Uploaded {len(bundle.get("entry", []))} IG resource(s) to HAPI. Response entries: {entry_count}.'
        ))
