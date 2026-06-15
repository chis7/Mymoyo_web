from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from locations.models import District, Facility, Province
from users.access import APPOINTMENT_ROLES, get_user_role
from users.models import Appointment, UserProfile

from .permissions import CanManageUsers, CanUseAppointments, IsActivePortalUser
from .serializers import (
    AppointmentSerializer,
    DistrictSerializer,
    FacilitySerializer,
    LoginSerializer,
    ProvinceSerializer,
    UserSerializer,
)


def _portal_links(user):
    role = get_user_role(user)
    links = [
        {'label': 'Home', 'path': '/app/'},
        {'label': 'Find a Clinic', 'path': '/app/facilities'},
        {'label': 'My Profile', 'path': '/app/profile'},
    ]
    if user.is_superuser or role in APPOINTMENT_ROLES:
        links.append({'label': 'Appointments', 'path': '/app/appointments'})
    if user.is_superuser or role in {'admin', 'supervisor'}:
        links.append({'label': 'Command Center', 'path': '/app/dashboard'})
    return links


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
        appointments = Appointment.objects.filter(beneficiary=request.user)
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


class ProvinceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = ProvinceSerializer

    def get_queryset(self):
        return Province.objects.annotate(facility_count=Count('districts__facilities')).order_by('name')


class DistrictViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = DistrictSerializer

    def get_queryset(self):
        queryset = District.objects.select_related('province')
        province_id = self.request.query_params.get('province')
        if province_id and province_id.isdigit():
            queryset = queryset.filter(province_id=province_id)
        return queryset


class FacilityViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsActivePortalUser]
    serializer_class = FacilitySerializer

    def get_queryset(self):
        queryset = Facility.objects.select_related('district__province')
        search_term = self.request.query_params.get('q', '').strip()
        province_id = self.request.query_params.get('province', '').strip()
        district_id = self.request.query_params.get('district', '').strip()
        level = self.request.query_params.get('level', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term)
                | Q(code__icontains=search_term)
                | Q(district__name__icontains=search_term)
                | Q(district__province__name__icontains=search_term)
            )
        if province_id.isdigit():
            queryset = queryset.filter(district__province_id=province_id)
        if district_id.isdigit():
            queryset = queryset.filter(district_id=district_id)
        if level:
            queryset = queryset.filter(level=level)

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
            'province',
            'district',
            'facility',
        )
        if self.request.user.is_superuser or get_user_role(self.request.user) in APPOINTMENT_ROLES:
            return queryset
        return queryset.filter(beneficiary=self.request.user)

    def perform_create(self, serializer):
        if self.request.user.is_superuser or get_user_role(self.request.user) in APPOINTMENT_ROLES:
            serializer.save()
        else:
            serializer.save(beneficiary=self.request.user)

    def perform_update(self, serializer):
        if not self.request.user.is_superuser and get_user_role(self.request.user) not in APPOINTMENT_ROLES:
            serializer.save(beneficiary=self.request.user)
        else:
            serializer.save()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanManageUsers]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.select_related('profile').order_by('username')
