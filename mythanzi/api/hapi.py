import copy
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import FHIRResourceVersion


logger = logging.getLogger(__name__)
LAST_HAPI_SYNC_ERROR = ''


class HAPIUnavailable(Exception):
    pass


def _error_detail(exc):
    if isinstance(exc, HTTPError):
        try:
            return exc.read().decode('utf-8', errors='replace')
        except Exception:
            return str(exc)
    return str(exc)


def get_last_hapi_sync_error():
    return LAST_HAPI_SYNC_ERROR


def _set_last_hapi_sync_error(detail):
    global LAST_HAPI_SYNC_ERROR
    LAST_HAPI_SYNC_ERROR = detail or ''


def hapi_sync_enabled():
    return bool(getattr(settings, 'HAPI_FHIR_SYNC_ENABLED', False) and settings.HAPI_FHIR_BASE_URL)


def check_hapi_available():
    if not hapi_sync_enabled():
        return False, 'HAPI sync is disabled or HAPI_FHIR_BASE_URL is empty.'

    url = f"{settings.HAPI_FHIR_BASE_URL.rstrip('/')}/metadata"
    try:
        _request_hapi('GET', url)
        return True, ''
    except HTTPError as exc:
        return False, _error_detail(exc)
    except (URLError, TimeoutError, OSError, RuntimeError) as exc:
        return False, str(exc)


def _resource_for_hapi(resource):
    payload = copy.deepcopy(resource)
    meta = payload.get('meta') or {}
    meta.pop('versionId', None)
    meta.pop('lastUpdated', None)
    if meta:
        payload['meta'] = meta
    else:
        payload.pop('meta', None)
    _repair_profile_person_link(payload)
    _repair_r5_appointment(payload)
    return payload


def _repair_profile_person_link(resource):
    """Move old Patient.link->Person mappings into an extension HAPI accepts."""
    if resource.get('resourceType') not in {'Patient', 'Practitioner'}:
        return

    valid_links = []
    person_references = []
    for link in resource.get('link', []) or []:
        reference = (link.get('other') or {}).get('reference', '')
        if reference.startswith('Person/'):
            person_references.append(link.get('other'))
        else:
            valid_links.append(link)

    if valid_links:
        resource['link'] = valid_links
    else:
        resource.pop('link', None)

    for reference in person_references:
        resource.setdefault('extension', []).append({
            'url': 'https://mythanzi.local/fhir/StructureDefinition/person-identity',
            'valueReference': reference,
        })


def _repair_r5_appointment(resource):
    """Convert old R4-ish Appointment fields into R5-compatible shapes."""
    if resource.get('resourceType') != 'Appointment':
        return

    service_types = []
    for item in resource.get('serviceType', []) or []:
        if 'concept' in item or 'reference' in item:
            service_types.append(item)
        elif 'text' in item:
            service_types.append({'concept': {'text': item['text']}})
        else:
            service_types.append(item)
    if service_types:
        resource['serviceType'] = service_types


def _hapi_url(resource_type, logical_id):
    base_url = settings.HAPI_FHIR_BASE_URL.rstrip('/')
    return f'{base_url}/{resource_type}/{logical_id}'


def _request_hapi(method, url, payload=None):
    data = None
    headers = {
        'Accept': 'application/fhir+json',
    }
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/fhir+json'

    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=settings.HAPI_FHIR_TIMEOUT_SECONDS) as response:
        if response.status not in {200, 201, 204}:
            raise RuntimeError(f'HAPI returned HTTP {response.status}')
        return response.status


def sync_fhir_version_to_hapi(version):
    if not hapi_sync_enabled():
        return False
    _set_last_hapi_sync_error('')

    url = _hapi_url(version.resource_type, version.logical_id)

    try:
        if version.action == FHIRResourceVersion.ACTION_DELETE:
            try:
                _request_hapi('DELETE', url)
            except HTTPError as exc:
                if exc.code != 404:
                    raise
        else:
            _request_hapi('PUT', url, _resource_for_hapi(version.resource))
        return True
    except HTTPError as exc:
        detail = _error_detail(exc)
        _set_last_hapi_sync_error(detail)
        logger.warning(
            'Could not sync FHIR resource %s/%s version %s to HAPI: %s',
            version.resource_type,
            version.logical_id,
            version.version_id,
            detail,
        )
        return False
    except (URLError, TimeoutError, OSError, RuntimeError) as exc:
        _set_last_hapi_sync_error(str(exc))
        logger.warning(
            'Could not reach HAPI while syncing FHIR resource %s/%s version %s: %s',
            version.resource_type,
            version.logical_id,
            version.version_id,
            exc,
        )
        return None
