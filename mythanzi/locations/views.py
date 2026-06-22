import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.views.decorators.http import require_POST

from users.access import USER_ADMIN_ROLES, active_login_required, role_required

from .forms import DistrictForm, FacilityForm, ProvinceForm, ServiceForm
from .models import District, Facility, Province, Service


FACILITY_MAP_RESULT_LIMIT = 99


LOCATION_MANAGEMENT_TABS = {
    'provinces': {
        'label': 'Provinces',
        'singular': 'Province',
        'icon': 'location_on',
    },
    'districts': {
        'label': 'Districts',
        'singular': 'District',
        'icon': 'public',
    },
    'services': {
        'label': 'Services',
        'singular': 'Service',
        'icon': 'medical_services',
    },
    'facilities': {
        'label': 'Facilities',
        'singular': 'Facility',
        'icon': 'local_hospital',
    },
}
LOCATION_VISIBLE_TABS = {
    key: value
    for key, value in LOCATION_MANAGEMENT_TABS.items()
    if key != 'services'
}

LOCATION_PAGE_SIZE_CHOICES = {10, 25, 50}

LOCATION_SORT_FIELDS = {
    'provinces': {
        'name': 'name',
        'districts': 'district_count',
        'facilities': 'facility_count',
    },
    'districts': {
        'name': 'name',
        'province': 'province__name',
        'facilities': 'facility_count',
    },
    'services': {
        'name': 'name',
        'code': 'code',
        'facilities': 'facility_count',
        'status': 'is_active',
    },
    'facilities': {
        'name': 'name',
        'code': 'code',
        'level': 'level',
        'district': 'district__name',
        'province': 'district__province__name',
        'services': 'service_count',
        'coordinates': 'latitude',
    },
}


def get_unmapped_facility_filter():
    return Q(latitude__isnull=True) | Q(longitude__isnull=True)


def get_location_page(queryset, page_number, per_page):
    paginator = Paginator(queryset, per_page)
    try:
        return paginator.page(page_number)
    except (EmptyPage, ValueError):
        return paginator.page(paginator.num_pages or 1)


def get_location_management_context(
    active_tab,
    search_term='',
    form=None,
    mapped_filter='',
    sort_key='name',
    sort_dir='asc',
    page_number=1,
    per_page=10,
    show_create_modal=False,
    visible_tabs=None,
    management_title='Manage Locations',
    management_description='Maintain provinces, districts, and facilities from the portal.',
    breadcrumb_current='Locations',
):
    provinces = Province.objects.annotate(
        district_count=Count('districts', distinct=True),
        facility_count=Count('districts__facilities', distinct=True),
    )
    districts = District.objects.select_related('province').annotate(
        facility_count=Count('facilities', distinct=True),
    )
    services = Service.objects.annotate(facility_count=Count('facilities', distinct=True))
    facilities = Facility.objects.select_related('district__province').prefetch_related('services').annotate(
        service_count=Count('services', distinct=True),
    )

    if search_term:
        provinces = provinces.filter(name__icontains=search_term)
        districts = districts.filter(
            Q(name__icontains=search_term) |
            Q(province__name__icontains=search_term)
        )
        services = services.filter(
            Q(name__icontains=search_term) |
            Q(code__icontains=search_term) |
            Q(description__icontains=search_term)
        )
        facilities = facilities.filter(
            Q(name__icontains=search_term) |
            Q(code__icontains=search_term) |
            Q(level__icontains=search_term) |
            Q(services__name__icontains=search_term) |
            Q(district__name__icontains=search_term) |
            Q(district__province__name__icontains=search_term)
        ).distinct()

    if active_tab == 'facilities' and mapped_filter == 'unmapped':
        facilities = facilities.filter(get_unmapped_facility_filter())

    unmapped_facility_count = Facility.objects.filter(get_unmapped_facility_filter()).count()
    active_queryset = {
        'provinces': provinces,
        'districts': districts,
        'services': services,
        'facilities': facilities,
    }[active_tab]
    sort_fields = LOCATION_SORT_FIELDS[active_tab]
    if sort_key not in sort_fields:
        sort_key = 'name'
    if sort_dir not in {'asc', 'desc'}:
        sort_dir = 'asc'

    order_field = sort_fields[sort_key]
    if sort_dir == 'desc':
        order_field = f'-{order_field}'
    active_queryset = active_queryset.order_by(order_field, 'pk')

    if per_page not in LOCATION_PAGE_SIZE_CHOICES:
        per_page = 10
    page_obj = get_location_page(active_queryset, page_number, per_page)

    return {
        'active_tab': active_tab,
        'active_tab_label': LOCATION_MANAGEMENT_TABS[active_tab]['label'],
        'active_tab_singular': LOCATION_MANAGEMENT_TABS[active_tab]['singular'],
        'tabs': visible_tabs or LOCATION_VISIBLE_TABS,
        'management_title': management_title,
        'management_description': management_description,
        'breadcrumb_current': breadcrumb_current,
        'is_service_management': active_tab == 'services',
        'search_term': search_term,
        'mapped_filter': mapped_filter,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'page_obj': page_obj,
        'page_size': per_page,
        'page_size_choices': sorted(LOCATION_PAGE_SIZE_CHOICES),
        'show_create_modal': show_create_modal,
        'province_form': form if active_tab == 'provinces' and form else ProvinceForm(),
        'district_form': form if active_tab == 'districts' and form else DistrictForm(),
        'service_form': form if active_tab == 'services' and form else ServiceForm(),
        'facility_form': form if active_tab == 'facilities' and form else FacilityForm(),
        'provinces': provinces,
        'districts': districts,
        'services': services,
        'facilities': facilities,
        'stats': {
            'provinces': Province.objects.count(),
            'districts': District.objects.count(),
            'services': Service.objects.count(),
            'facilities': Facility.objects.count(),
            'mapped': Facility.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count(),
            'unmapped': unmapped_facility_count,
        },
    }


def get_location_model_and_form(tab):
    return {
        'provinces': (Province, ProvinceForm),
        'districts': (District, DistrictForm),
        'services': (Service, ServiceForm),
        'facilities': (Facility, FacilityForm),
    }[tab]


@role_required(*USER_ADMIN_ROLES)
def location_management(request, tab='provinces'):
    if tab == 'services':
        return redirect('service_management')
    if tab not in LOCATION_VISIBLE_TABS:
        return redirect('location_management')

    search_term = request.GET.get('q', '').strip()
    mapped_filter = request.GET.get('mapped', '').strip()
    if mapped_filter not in {'', 'unmapped'}:
        mapped_filter = ''
    sort_key = request.GET.get('sort', 'name').strip()
    sort_dir = request.GET.get('dir', 'asc').strip()
    try:
        page_number = max(int(request.GET.get('page', 1)), 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        per_page = int(request.GET.get('per_page', 10))
    except (TypeError, ValueError):
        per_page = 10
    form_class = {
        'provinces': ProvinceForm,
        'districts': DistrictForm,
        'services': ServiceForm,
        'facilities': FacilityForm,
    }[tab]

    form = None
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"{LOCATION_MANAGEMENT_TABS[tab]['singular']} saved successfully.")
            return redirect('location_management_tab', tab=tab)
        messages.error(request, 'Please correct the highlighted fields.')
        show_create_modal = True
    else:
        show_create_modal = False

    return render(
        request,
        'locations/location_management.html',
        get_location_management_context(
            tab,
            search_term,
            form,
            mapped_filter,
            sort_key,
            sort_dir,
            page_number,
            per_page,
            show_create_modal,
            LOCATION_VISIBLE_TABS,
        ),
    )


@role_required(*USER_ADMIN_ROLES)
def service_management(request):
    search_term = request.GET.get('q', '').strip()
    sort_key = request.GET.get('sort', 'name').strip()
    sort_dir = request.GET.get('dir', 'asc').strip()
    try:
        page_number = max(int(request.GET.get('page', 1)), 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        per_page = int(request.GET.get('per_page', 10))
    except (TypeError, ValueError):
        per_page = 10

    form = None
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service saved successfully.')
            return redirect('service_management')
        messages.error(request, 'Please correct the highlighted fields.')
        show_create_modal = True
    else:
        show_create_modal = False

    return render(
        request,
        'locations/location_management.html',
        get_location_management_context(
            'services',
            search_term,
            form,
            '',
            sort_key,
            sort_dir,
            page_number,
            per_page,
            show_create_modal,
            {'services': LOCATION_MANAGEMENT_TABS['services']},
            'Manage Services',
            'Maintain services and map facilities to what they provide.',
            'Services',
        ),
    )


@role_required(*USER_ADMIN_ROLES)
def location_edit(request, tab, pk):
    if tab not in LOCATION_MANAGEMENT_TABS:
        return redirect('location_management')

    model, form_class = get_location_model_and_form(tab)
    location_object = get_object_or_404(model, pk=pk)
    form = form_class(request.POST or None, instance=location_object)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f"{LOCATION_MANAGEMENT_TABS[tab]['singular']} updated successfully.")
        if tab == 'services':
            return redirect('service_management')
        return redirect('location_management_tab', tab=tab)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'locations/_location_form_fields.html', {
            'form': form,
            'action_url': request.path,
            'submit_label': 'Save Changes',
        })

    return render(request, 'locations/location_form.html', {
        'active_tab': tab,
        'active_tab_label': LOCATION_MANAGEMENT_TABS[tab]['label'],
        'active_tab_singular': LOCATION_MANAGEMENT_TABS[tab]['singular'],
        'form': form,
        'location_object': location_object,
        'management_url_name': 'service_management' if tab == 'services' else 'location_management_tab',
    })


@role_required(*USER_ADMIN_ROLES)
@require_POST
def location_delete(request, tab, pk):
    if tab not in LOCATION_MANAGEMENT_TABS:
        return redirect('location_management')

    model, _ = get_location_model_and_form(tab)
    location_object = get_object_or_404(model, pk=pk)
    object_name = str(location_object)
    try:
        location_object.delete()
    except (ProtectedError, IntegrityError):
        messages.error(
            request,
            f'{LOCATION_MANAGEMENT_TABS[tab]["singular"]} "{object_name}" cannot be deleted because it is still referenced.',
        )
    else:
        messages.success(request, f'{LOCATION_MANAGEMENT_TABS[tab]["singular"]} "{object_name}" deleted successfully.')
    if tab == 'services':
        return redirect('service_management')
    return redirect('location_management_tab', tab=tab)


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
