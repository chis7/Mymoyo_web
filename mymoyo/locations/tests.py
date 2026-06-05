from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .models import District, Facility, Province


class FacilityMapTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='clinic-user', password='test-password')
        self.province = Province.objects.create(name='Central')
        self.other_province = Province.objects.create(name='Eastern')
        self.district = District.objects.create(name='Chibombo', province=self.province)
        self.other_district = District.objects.create(name='Chipata', province=self.other_province)
        self.facility = Facility.objects.create(
            name='Chibombo Rural Health Centre',
            district=self.district,
            code='1777',
            level='Health Centre',
            latitude='-14.6500000',
            longitude='28.0500000',
        )
        Facility.objects.create(
            name='Chipata Clinic',
            district=self.other_district,
            code='2000',
            level='Clinic',
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('facility_map'))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('facility_map')}")

    def test_authenticated_user_can_view_facility_map(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('facility_map'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find a Clinic')
        self.assertContains(response, self.facility.name)
        self.assertEqual(response.context['mapped_count'], 1)
        self.assertContains(response, 'facility-map-data')
        self.assertContains(response, 'all-facility-map-data')
        self.assertNotContains(response, 'leaflet.markercluster')
        self.assertContains(response, 'L.layerGroup()')
        self.assertContains(response, 'device-location-marker')
        self.assertContains(response, "marker.on('click'")
        self.assertContains(response, 'routeToFacility')
        self.assertContains(response, 'routeSummaryClose')
        self.assertContains(response, 'facilityRadiusKm = 5')
        self.assertContains(response, 'Top 3 clinics within 5 km')
        self.assertContains(response, 'const candidates = getFacilitiesWithinRadius(visibleFacilities)')
        self.assertContains(response, 'hasActiveFilters()')
        self.assertContains(response, "heading.textContent = 'Search results'")
        self.assertContains(response, "getFacilityCardMarkup(facility, 'kanban js-search-facility', null, false)")
        self.assertContains(response, 'visibleFacilities = hasActiveFilters()')
        self.assertContains(response, 'resultFacilities = data.facilities')
        self.assertContains(response, 'data-clear-filter="q"')
        self.assertContains(response, 'data-clear-filter="province"')
        self.assertContains(response, 'data-clear-filter="district"')
        self.assertContains(response, 'data-clear-filter="level"')
        self.assertContains(response, 'function clearClinicFilters()')
        self.assertContains(response, 'function updateFilterClearButtons()')
        self.assertContains(response, "'Satellite'")
        self.assertNotContains(response, 'estimated travel time')

    def test_facility_map_filters_by_province_and_search_term(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('facility_map'), {
            'province': self.province.pk,
            'q': '1777',
        })

        self.assertContains(response, self.facility.name)
        self.assertNotContains(response, 'Chipata Clinic')

    def test_facility_map_ignores_invalid_location_ids(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('facility_map'), {
            'province': 'invalid',
            'district': 'invalid',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.facility.name)

    def test_anonymous_user_cannot_access_async_results(self):
        response = self.client.get(reverse('facility_map_results'))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('facility_map_results')}")

    def test_async_results_filter_facilities_and_districts(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('facility_map_results'), {
            'province': self.province.pk,
            'q': '1777',
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['result_count'], 1)
        self.assertEqual(data['facilities'][0]['name'], self.facility.name)
        self.assertEqual(data['mapped_facilities'][0]['latitude'], -14.65)
        self.assertEqual(data['districts'], [{'id': self.district.pk, 'name': self.district.name}])

    def test_import_command_updates_existing_facility_coordinates(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['MFL Code', 'Name', 'Province', 'District', 'Type', 'Latitude', 'Longitude'])
        sheet.append([
            '1777',
            self.facility.name,
            self.province.name,
            self.district.name,
            'Health Centre',
            '-14.44888262',
            ' 22.76034052\t',
        ])

        with NamedTemporaryFile(suffix='.xlsx') as export:
            workbook.save(export.name)
            call_command('import_locations', Path(export.name))

        self.facility.refresh_from_db()
        self.assertEqual(str(self.facility.latitude), '-14.4488826')
        self.assertEqual(str(self.facility.longitude), '22.7603405')
