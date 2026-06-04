import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from users.access import active_login_required

from .models import District, Facility, Province


FACILITY_MAP_RESULT_LIMIT = 99


def get_facility_filters(request):
    search_term = request.GET.get('q', '').strip()
    province_id = request.GET.get('province', '').strip()
    district_id = request.GET.get('district', '').strip()
    level = request.GET.get('level', '').strip()

    if province_id and not province_id.isdigit():
        province_id = ''
    if district_id and not district_id.isdigit():
        district_id = ''

    return search_term, province_id, district_id, level


def get_filtered_facilities(search_term, province_id, district_id, level):
    facilities = Facility.objects.select_related('district__province')
    if search_term:
        facilities = facilities.filter(
            Q(name__icontains=search_term) |
            Q(code__icontains=search_term) |
            Q(district__name__icontains=search_term) |
            Q(district__province__name__icontains=search_term)
        )
    if province_id:
        facilities = facilities.filter(district__province_id=province_id)
    if district_id:
        facilities = facilities.filter(district_id=district_id)
    if level:
        facilities = facilities.filter(level=level)
    return facilities


def serialize_facility(facility):
    return {
        'name': facility.name,
        'district': facility.district.name,
        'province': facility.district.province.name,
        'level': facility.level or '',
        'code': facility.code or '',
        'latitude': float(facility.latitude) if facility.latitude is not None else None,
        'longitude': float(facility.longitude) if facility.longitude is not None else None,
    }


def serialize_mapped_facilities(facilities):
    return [
        {
            'name': facility.name,
            'district': facility.district.name,
            'province': facility.district.province.name,
            'level': facility.level or '',
            'code': facility.code or '',
            'latitude': float(facility.latitude),
            'longitude': float(facility.longitude),
        }
        for facility in facilities.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    ]


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_valid_coordinate(latitude, longitude):
    return (
        latitude is not None and longitude is not None and
        -90 <= latitude <= 90 and -180 <= longitude <= 180
    )


@active_login_required
def facility_map(request):
    search_term, province_id, district_id, level = get_facility_filters(request)
    facilities = get_filtered_facilities(search_term, province_id, district_id, level)
    provinces = Province.objects.annotate(facility_count=Count('districts__facilities'))
    mapped_facilities = serialize_mapped_facilities(facilities)
    all_mapped_facilities = serialize_mapped_facilities(Facility.objects.select_related('district__province'))
    districts = District.objects.select_related('province')
    if province_id:
        districts = districts.filter(province_id=province_id)

    level_choices = Facility.objects.exclude(level__isnull=True).exclude(level='').values_list(
        'level',
        flat=True,
    ).distinct().order_by('level')
    result_count = facilities.count()
    result_facilities = list(facilities[:FACILITY_MAP_RESULT_LIMIT])

    context = {
        'facilities': result_facilities,
        'result_facilities': [serialize_facility(facility) for facility in result_facilities],
        'result_count': result_count,
        'showing_limit': min(result_count, FACILITY_MAP_RESULT_LIMIT),
        'provinces': provinces,
        'mapped_facilities': mapped_facilities,
        'all_mapped_facilities': all_mapped_facilities,
        'mapped_count': len(mapped_facilities),
        'districts': districts,
        'level_choices': level_choices,
        'search_term': search_term,
        'selected_province': province_id,
        'selected_district': district_id,
        'selected_level': level,
    }
    return render(request, 'locations/facility_map.html', context)


@active_login_required
@require_POST
def facility_road_distances(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    origin = payload.get('origin') or {}
    origin_latitude = parse_float(origin.get('latitude'))
    origin_longitude = parse_float(origin.get('longitude'))
    if not is_valid_coordinate(origin_latitude, origin_longitude):
        return JsonResponse({'error': 'A valid origin latitude and longitude is required.'}, status=400)

    candidates = []
    for index, candidate in enumerate(payload.get('candidates') or []):
        latitude = parse_float(candidate.get('latitude'))
        longitude = parse_float(candidate.get('longitude'))
        if is_valid_coordinate(latitude, longitude):
            candidates.append({
                'index': index,
                'latitude': latitude,
                'longitude': longitude,
            })

    limit = settings.OSRM_DISTANCE_CANDIDATE_LIMIT
    candidates = candidates[:limit]
    if not candidates:
        return JsonResponse({'distances': []})

    coordinates = [f'{origin_longitude},{origin_latitude}'] + [
        f"{candidate['longitude']},{candidate['latitude']}"
        for candidate in candidates
    ]
    query = urlencode({
        'sources': '0',
        'annotations': 'distance,duration',
    })
    osrm_url = (
        f'{settings.OSRM_BASE_URL}/table/v1/{settings.OSRM_ROUTE_PROFILE}/'
        f"{';'.join(coordinates)}?{query}"
    )

    try:
        with urlopen(osrm_url, timeout=10) as response:
            osrm_data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return JsonResponse({
            'error': 'Road distance service is unavailable.',
            'detail': str(error),
        }, status=503)

    distances = (osrm_data.get('distances') or [[]])[0]
    durations = (osrm_data.get('durations') or [[]])[0]
    return JsonResponse({
        'distances': [
            {
                'index': candidate['index'],
                'distance_km': None if distances[offset] is None else distances[offset] / 1000,
                'duration_seconds': None if durations[offset] is None else durations[offset],
            }
            for offset, candidate in enumerate(candidates, start=1)
            if offset < len(distances)
        ],
    })


@active_login_required
@require_POST
def facility_directions(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    origin = payload.get('origin') or {}
    destination = payload.get('destination') or {}
    origin_latitude = parse_float(origin.get('latitude'))
    origin_longitude = parse_float(origin.get('longitude'))
    destination_latitude = parse_float(destination.get('latitude'))
    destination_longitude = parse_float(destination.get('longitude'))
    if not is_valid_coordinate(origin_latitude, origin_longitude):
        return JsonResponse({'error': 'A valid origin latitude and longitude is required.'}, status=400)
    if not is_valid_coordinate(destination_latitude, destination_longitude):
        return JsonResponse({'error': 'A valid destination latitude and longitude is required.'}, status=400)

    coordinates = (
        f'{origin_longitude},{origin_latitude};'
        f'{destination_longitude},{destination_latitude}'
    )
    query = urlencode({
        'overview': 'full',
        'geometries': 'geojson',
        'steps': 'true',
    })
    osrm_url = (
        f'{settings.OSRM_BASE_URL}/route/v1/{settings.OSRM_ROUTE_PROFILE}/'
        f'{coordinates}?{query}'
    )

    try:
        with urlopen(osrm_url, timeout=10) as response:
            osrm_data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return JsonResponse({
            'error': 'Directions service is unavailable.',
            'detail': str(error),
        }, status=503)

    route = (osrm_data.get('routes') or [None])[0]
    if not route:
        return JsonResponse({'error': 'No route found.'}, status=404)

    return JsonResponse({
        'distance_km': route.get('distance', 0) / 1000,
        'duration_seconds': route.get('duration', 0),
        'geometry': route.get('geometry'),
        'steps': [
            {
                'name': step.get('name') or '',
                'distance_km': step.get('distance', 0) / 1000,
                'duration_seconds': step.get('duration', 0),
                'instruction': (step.get('maneuver') or {}).get('type', ''),
            }
            for leg in route.get('legs') or []
            for step in leg.get('steps') or []
        ],
    })


@active_login_required
def facility_map_results(request):
    search_term, province_id, district_id, level = get_facility_filters(request)
    facilities = get_filtered_facilities(search_term, province_id, district_id, level)
    result_count = facilities.count()
    districts = District.objects.select_related('province')
    if province_id:
        districts = districts.filter(province_id=province_id)

    return JsonResponse({
        'facilities': [serialize_facility(facility) for facility in facilities[:FACILITY_MAP_RESULT_LIMIT]],
        'mapped_facilities': serialize_mapped_facilities(facilities),
        'result_count': result_count,
        'showing_limit': min(result_count, FACILITY_MAP_RESULT_LIMIT),
        'districts': [
            {'id': district.pk, 'name': district.name}
            for district in districts
        ],
    })
