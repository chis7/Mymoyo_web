from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from locations.models import District, Facility, Province, Service
from users.access import APPOINTMENT_ROLES, USER_ADMIN_ROLES, get_user_role, visible_appointment_filter
from users.models import (
    Appointment,
    ClientConsent,
    ClientJourneyEvent,
    ClientLocator,
    FollowUpTask,
    Notification,
    ReferralRecord,
    UserProfile,
)
from users.notifications import (
    notify_appointment_created,
    notify_appointment_deleted,
    notify_appointment_updated,
    notify_follow_up_task_created,
    notify_follow_up_task_deleted,
    notify_follow_up_task_updated,
    notify_journey_event_created,
    notify_journey_event_deleted,
    notify_journey_event_updated,
    notify_referral_created,
    notify_referral_deleted,
    notify_referral_updated,
)

from .fhir import latest_resources
from .models import FHIRResourceVersion
from .permissions import CanManageUsers, CanUseAppointments, IsActivePortalUser
from .serializers import (
    AppointmentSerializer,
    ClientConsentSerializer,
    ClientDetailSerializer,
    ClientJourneyEventSerializer,
    ClientLocatorSerializer,
    ClientSummarySerializer,
    DistrictSerializer,
    FHIRResourceVersionSerializer,
    FacilitySerializer,
    FollowUpTaskSerializer,
    LoginSerializer,
    NotificationSerializer,
    ProvinceSerializer,
    ReferralRecordSerializer,
    ServiceSerializer,
    UserSerializer,
)


FHIR_ALLOWED_RESOURCE_TYPES = {'Appointment', 'HealthcareService', 'Location', 'Patient', 'Person', 'Practitioner', 'Provenance'}


def _fhir_bundle(request, resources, bundle_type='searchset'):
    return {
        'resourceType': 'Bundle',
        'type': bundle_type,
        'total': len(resources),
        'entry': [
            {
                'fullUrl': request.build_absolute_uri(
                    f"/api/fhir/{resource['resourceType']}/{resource['id']}/"
                ),
                'resource': resource,
            }
            for resource in resources
        ],
    }


def _portal_links(user):
    role = get_user_role(user)
    links = [
        {'label': 'Home', 'path': '/app/'},
        {'label': 'Find a Clinic', 'path': '/app/facilities'},
        {'label': 'Notifications', 'path': '/app/notifications'},
        {'label': 'My Profile', 'path': '/app/profile'},
    ]
    if user.is_superuser or role in APPOINTMENT_ROLES or role == 'client':
        links.append({'label': 'Appointments', 'path': '/app/appointments'})
    if user.is_superuser or role in APPOINTMENT_ROLES:
        links.append({'label': 'Clients', 'path': '/app/clients'})
    if user.is_superuser or role in {'admin', 'supervisor'}:
        links.append({'label': 'Command Center', 'path': '/app/dashboard'})
    if user.is_superuser or role == 'admin':
        links.append({'label': 'Locations', 'path': '/app/locations'})
    return links


def _visible_clients(user):
    clients = User.objects.select_related(
        'profile__facility',
        'profile__person_identity',
        'profile__population_group',
        'client_locator__service_point',
        'client_consent',
    ).filter(
        profile__role='client',
        profile__is_active=True,
        is_active=True,
    )
    role = get_user_role(user)

    if user.is_superuser or role in USER_ADMIN_ROLES or role == 'supervisor':
        return clients

    if role in APPOINTMENT_ROLES:
        facility_id = getattr(getattr(user, 'profile', None), 'facility_id', None)
        if facility_id:
            return clients.filter(
                Q(profile__facility_id=facility_id)
                | Q(appointments__facility_id=facility_id)
                | Q(client_locator__service_point_id=facility_id)
            ).distinct()

        return clients.filter(
            Q(appointments__created_by=user)
            | Q(follow_up_tasks__assigned_to=user)
        ).distinct()

    return clients.filter(pk=user.pk)


class CsrfTokenView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request,
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
        )
        if user is None:
            return Response({'detail': 'Invalid username or password.'}, status=status.HTTP_400_BAD_REQUEST)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.is_active:
            return Response({'detail': 'This account has been disabled.'}, status=status.HTTP_403_FORBIDDEN)

        login(request, user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'must_change_password': profile.must_change_password,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.auth:
            request.auth.delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsActivePortalUser]

    def get(self, request):
        return Response({
            'user': UserSerializer(request.user).data,
            'navigation': _portal_links(request.user),
        })


class AppBootstrapView(APIView):
    permission_classes = [IsActivePortalUser]

    def get(self, request):
        role = get_user_role(request.user)
        if request.user.is_superuser or role in USER_ADMIN_ROLES:
            appointments = Appointment.objects.all()
        else:
            appointments = Appointment.objects.filter(visible_appointment_filter(request.user))
        return Response({
            'user': UserSerializer(request.user).data,
            'navigation': _portal_links(request.user),
            'appointment_summary': {
                'upcoming': appointments.filter(status='upcoming').count(),
                'completed': appointments.filter(status='completed').count(),
                'missed': appointments.filter(status='missed').count(),
            },
            'offline_content': {
                'prevention_methods': [
                    {'name': 'Oral PrEP', 'schedule': 'Daily'},
                    {'name': 'CAB-LA Injectable', 'schedule': 'Every 2 months'},
                    {'name': 'Dapivirine Ring', 'schedule': 'Monthly'},
                    {'name': 'Lenacapavir Injectable', 'schedule': 'Every 6 months'},
                    {'name': 'Event-Driven PrEP', 'schedule': 'Before and after sex'},
                ],
            },
        })


class DashboardStatsView(APIView):
    permission_classes = [IsActivePortalUser]

    def get(self, request):
        if not request.user.is_superuser and get_user_role(request.user) not in {'admin', 'supervisor'}:
            raise PermissionDenied('You do not have access to dashboard statistics.')
        total_facilities = Facility.objects.count()
        mapped_facilities = Facility.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
        appointments = Appointment.objects.all()
        role_counts = UserProfile.objects.values('role').annotate(count=Count('pk'))
        return Response({
            'cards': [
                {
                    'title': 'Users',
                    'value': User.objects.count(),
                    'meta': f"{User.objects.filter(is_active=True).count()} active",
                    'path': '/users',
                },
                {
                    'title': 'Locations',
                    'value': total_facilities,
                    'meta': f"{Province.objects.count()} provinces, {District.objects.count()} districts",
                    'path': '/locations',
                },
                {
                    'title': 'Mapped Facilities',
                    'value': mapped_facilities,
                    'meta': f"{max(total_facilities - mapped_facilities, 0)} unmapped",
                    'path': '/locations?tab=facilities&mapped=unmapped',
                },
                {
                    'title': 'Appointments',
                    'value': appointments.count(),
                    'meta': f"{appointments.filter(status='upcoming').count()} upcoming",
                    'path': '/appointments',
                },
            ],
            'roles': [
                {
                    'role': role_key,
                    'label': role_label,
                    'count': next((item['count'] for item in role_counts if item['role'] == role_key), 0),
                }
                for role_key, role_label in UserProfile.ROLE_CHOICES
            ],
        })


class FHIRResourceListView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request, resource_type=None):
        if resource_type and resource_type not in FHIR_ALLOWED_RESOURCE_TYPES:
            return Response({'detail': 'Unsupported FHIR resource type.'}, status=status.HTTP_404_NOT_FOUND)

        versions = latest_resources(resource_type)
        resources = [version.resource for version in versions]
        return Response(_fhir_bundle(request, resources))


class FHIRResourceDetailView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request, resource_type, logical_id):
        if resource_type not in FHIR_ALLOWED_RESOURCE_TYPES:
            return Response({'detail': 'Unsupported FHIR resource type.'}, status=status.HTTP_404_NOT_FOUND)

        version = (
            FHIRResourceVersion.objects
            .filter(resource_type=resource_type, logical_id=logical_id)
            .order_by('-version_id')
            .first()
        )
        if not version:
            return Response({'detail': 'FHIR resource not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(version.resource)


class FHIRResourceHistoryView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request, resource_type, logical_id):
        if resource_type not in FHIR_ALLOWED_RESOURCE_TYPES:
            return Response({'detail': 'Unsupported FHIR resource type.'}, status=status.HTTP_404_NOT_FOUND)

        versions = FHIRResourceVersion.objects.filter(
            resource_type=resource_type,
            logical_id=logical_id,
        ).order_by('-version_id')
        resources = [version.resource for version in versions]
        return Response(_fhir_bundle(request, resources, bundle_type='history'))


class FHIRResourceVersionView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request, resource_type, logical_id, version_id):
        if resource_type not in FHIR_ALLOWED_RESOURCE_TYPES:
            return Response({'detail': 'Unsupported FHIR resource type.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            version = FHIRResourceVersion.objects.get(
                resource_type=resource_type,
                logical_id=logical_id,
                version_id=version_id,
            )
        except FHIRResourceVersion.DoesNotExist:
            return Response({'detail': 'FHIR resource version not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(version.resource)


class FHIRResourceVersionAuditView(APIView):
    permission_classes = [CanManageUsers]

    def get(self, request):
        queryset = FHIRResourceVersion.objects.order_by('-recorded_at')
        resource_type = request.query_params.get('resource_type', '').strip()
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        serializer = FHIRResourceVersionSerializer(queryset[:100], many=True)
        return Response(serializer.data)


class AdminWriteOrActiveReadMixin:
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsActivePortalUser()]
        return [CanManageUsers()]


class ProvinceViewSet(AdminWriteOrActiveReadMixin, viewsets.ModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = ProvinceSerializer

    def get_queryset(self):
        queryset = Province.objects.annotate(facility_count=Count('districts__facilities')).order_by('name')
        ordering = self.request.query_params.get('ordering', '').strip()
        allowed = {'name', '-name', 'facility_count', '-facility_count'}
        if ordering in allowed:
            queryset = queryset.order_by(ordering)
        return queryset


class DistrictViewSet(AdminWriteOrActiveReadMixin, viewsets.ModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = DistrictSerializer

    def get_queryset(self):
        queryset = District.objects.select_related('province')
        province_id = self.request.query_params.get('province')
        if province_id and province_id.isdigit():
            queryset = queryset.filter(province_id=province_id)
        ordering = self.request.query_params.get('ordering', '').strip()
        allowed = {'name', '-name', 'province__name', '-province__name'}
        if ordering in allowed:
            queryset = queryset.order_by(ordering, 'name')
        return queryset


class ServiceViewSet(AdminWriteOrActiveReadMixin, viewsets.ModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        queryset = Service.objects.annotate(facility_count=Count('facilities', distinct=True))
        search_term = self.request.query_params.get('q', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term)
                | Q(code__icontains=search_term)
                | Q(description__icontains=search_term)
            )
        ordering = self.request.query_params.get('ordering', '').strip()
        allowed = {'name', '-name', 'code', '-code', 'facility_count', '-facility_count', 'is_active', '-is_active'}
        if ordering in allowed:
            queryset = queryset.order_by(ordering, 'name')
        else:
            queryset = queryset.order_by('name')
        return queryset


class FacilityViewSet(AdminWriteOrActiveReadMixin, viewsets.ModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = FacilitySerializer

    def get_queryset(self):
        queryset = Facility.objects.select_related('district__province', 'hub').prefetch_related('services').annotate(
            spoke_count=Count('spokes', distinct=True),
        )
        search_term = self.request.query_params.get('q', '').strip()
        province_id = self.request.query_params.get('province', '').strip()
        district_id = self.request.query_params.get('district', '').strip()
        service_code = self.request.query_params.get('service', '').strip()
        level = self.request.query_params.get('level', '').strip()
        facility_type = self.request.query_params.get('facility_type', '').strip()
        hub_id = self.request.query_params.get('hub', '').strip()
        mapped = self.request.query_params.get('mapped', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term)
                | Q(code__icontains=search_term)
                | Q(services__name__icontains=search_term)
                | Q(district__name__icontains=search_term)
                | Q(district__province__name__icontains=search_term)
            ).distinct()
        if province_id.isdigit():
            queryset = queryset.filter(district__province_id=province_id)
        if district_id.isdigit():
            queryset = queryset.filter(district_id=district_id)
        if service_code:
            queryset = queryset.filter(services__code=service_code, services__is_active=True)
        if level:
            queryset = queryset.filter(level=level)
        if facility_type:
            queryset = queryset.filter(facility_type=facility_type)
        if hub_id.isdigit():
            queryset = queryset.filter(hub_id=hub_id)
        if mapped == 'unmapped':
            queryset = queryset.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True))
        ordering = self.request.query_params.get('ordering', '').strip()
        allowed = {
            'name',
            '-name',
            'code',
            '-code',
            'level',
            '-level',
            'facility_type',
            '-facility_type',
            'hub__name',
            '-hub__name',
            'spoke_count',
            '-spoke_count',
            'district__name',
            '-district__name',
            'district__province__name',
            '-district__province__name',
            'latitude',
            '-latitude',
        }
        if ordering in allowed:
            queryset = queryset.order_by(ordering, 'name')

        return queryset

    @action(detail=False, methods=['get'])
    def levels(self, request):
        levels = (
            Facility.objects.exclude(level__isnull=True)
            .exclude(level='')
            .values_list('level', flat=True)
            .distinct()
            .order_by('level')
        )
        return Response({'levels': list(levels)})


class AppointmentViewSet(viewsets.ModelViewSet):
    permission_classes = [CanUseAppointments]
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        queryset = Appointment.objects.select_related(
            'beneficiary__profile',
            'created_by__profile',
            'province',
            'district',
            'facility',
        )
        return queryset.filter(visible_appointment_filter(self.request.user))

    def perform_create(self, serializer):
        if self.request.user.is_superuser or get_user_role(self.request.user) in APPOINTMENT_ROLES:
            appointment = serializer.save(created_by=self.request.user)
        else:
            appointment = serializer.save(beneficiary=self.request.user)
        notify_appointment_created(appointment, actor=self.request.user)

    def perform_update(self, serializer):
        if not self.request.user.is_superuser and get_user_role(self.request.user) not in APPOINTMENT_ROLES:
            appointment = serializer.save(beneficiary=self.request.user)
        else:
            appointment = serializer.save()
        notify_appointment_updated(appointment, actor=self.request.user)

    def perform_destroy(self, instance):
        notify_appointment_deleted(instance, actor=self.request.user)
        instance.delete()


class ClientManagementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanUseAppointments]

    def get_serializer_class(self):
        if self.action == 'list':
            return ClientSummarySerializer
        return ClientDetailSerializer

    def get_queryset(self):
        queryset = _visible_clients(self.request.user).annotate(
            journey_count=Count('journey_events', distinct=True),
            referral_count=Count('referral_records', distinct=True),
            follow_up_count=Count('follow_up_tasks', distinct=True),
            appointment_count=Count('appointments', distinct=True),
        ).prefetch_related(
            'journey_events__recorded_by',
            'referral_records__receiving_facility',
            'referral_records__assigned_mobiliser',
            'follow_up_tasks__assigned_to',
            'appointments__facility',
            'appointments__district',
            'appointments__province',
            'appointments__created_by__profile',
            'appointments__beneficiary__profile',
        )
        search_term = self.request.query_params.get('q', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term)
                | Q(first_name__icontains=search_term)
                | Q(last_name__icontains=search_term)
                | Q(profile__reference_number__icontains=search_term)
                | Q(profile__phone__icontains=search_term)
            )
        return queryset.order_by('first_name', 'last_name', 'username')

    def _client(self):
        return self.get_object()

    def _client_object(self, related_name, object_id):
        return get_object_or_404(getattr(self._client(), related_name), pk=object_id)

    @action(detail=True, methods=['post'], url_path='locator')
    def locator(self, request, pk=None):
        client = self._client()
        instance, _ = ClientLocator.objects.get_or_create(client=client)
        serializer = ClientLocatorSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='consent')
    def consent(self, request, pk=None):
        client = self._client()
        instance, _ = ClientConsent.objects.get_or_create(client=client)
        serializer = ClientConsentSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(recorded_by=request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='journey-events')
    def journey_events(self, request, pk=None):
        client = self._client()
        serializer = ClientJourneyEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save(client=client, recorded_by=request.user)
        notify_journey_event_created(event, actor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'journey-events/(?P<event_id>\d+)')
    def journey_event_detail(self, request, pk=None, event_id=None):
        event = self._client_object('journey_events', event_id)
        if request.method == 'DELETE':
            notify_journey_event_deleted(event, actor=request.user)
            event.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = ClientJourneyEventSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        notify_journey_event_updated(event, actor=request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='referrals')
    def referrals(self, request, pk=None):
        client = self._client()
        serializer = ReferralRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        referral = serializer.save(client=client, recorded_by=request.user)
        notify_referral_created(referral, actor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'referrals/(?P<referral_id>\d+)')
    def referral_detail(self, request, pk=None, referral_id=None):
        referral = self._client_object('referral_records', referral_id)
        if request.method == 'DELETE':
            notify_referral_deleted(referral, actor=request.user)
            referral.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = ReferralRecordSerializer(referral, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        referral = serializer.save(confirmed_by=request.user)
        notify_referral_updated(referral, actor=request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='follow-up-tasks')
    def follow_up_tasks(self, request, pk=None):
        client = self._client()
        serializer = FollowUpTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(client=client, created_by=request.user)
        notify_follow_up_task_created(task, actor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'follow-up-tasks/(?P<task_id>\d+)')
    def follow_up_task_detail(self, request, pk=None, task_id=None):
        task = self._client_object('follow_up_tasks', task_id)
        if request.method == 'DELETE':
            notify_follow_up_task_deleted(task, actor=request.user)
            task.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = FollowUpTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        notify_follow_up_task_updated(task, actor=request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='appointments')
    def appointments(self, request, pk=None):
        client = self._client()
        serializer = AppointmentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save(beneficiary=client, created_by=request.user)
        notify_appointment_created(appointment, actor=request.user)
        return Response(AppointmentSerializer(appointment, context={'request': request}).data, status=status.HTTP_201_CREATED)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanManageUsers]
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = User.objects.select_related('profile').order_by('username')
        search_term = self.request.query_params.get('q', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term)
                | Q(first_name__icontains=search_term)
                | Q(last_name__icontains=search_term)
                | Q(email__icontains=search_term)
                | Q(profile__reference_number__icontains=search_term)
            )
        return queryset


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.select_related(
            'appointment__beneficiary__profile',
            'appointment__created_by__profile',
            'appointment__province',
            'appointment__district',
            'appointment__facility',
        ).filter(
            recipient=self.request.user,
            channel='portal',
        ).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.get_queryset()
        return Response({
            'unread_count': queryset.filter(read_at__isnull=True).count(),
            'results': self.get_serializer(queryset[:5], many=True).data,
        })

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_read()
        return Response(self.get_serializer(notification).data)
