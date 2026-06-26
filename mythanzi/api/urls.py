from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AppBootstrapView,
    AppointmentViewSet,
    ClientManagementViewSet,
    CsrfTokenView,
    DashboardStatsView,
    DistrictViewSet,
    FHIRResourceDetailView,
    FHIRResourceHistoryView,
    FHIRResourceListView,
    FHIRResourceVersionAuditView,
    FHIRResourceVersionView,
    FacilityViewSet,
    LoginView,
    LogoutView,
    MeView,
    NotificationViewSet,
    ProvinceViewSet,
    ServiceViewSet,
    UserViewSet,
)


router = DefaultRouter()
router.register('appointments', AppointmentViewSet, basename='api-appointments')
router.register('clients', ClientManagementViewSet, basename='api-clients')
router.register('districts', DistrictViewSet, basename='api-districts')
router.register('facilities', FacilityViewSet, basename='api-facilities')
router.register('notifications', NotificationViewSet, basename='api-notifications')
router.register('provinces', ProvinceViewSet, basename='api-provinces')
router.register('services', ServiceViewSet, basename='api-services')
router.register('users', UserViewSet, basename='api-users')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/csrf/', CsrfTokenView.as_view(), name='api-csrf'),
    path('auth/login/', LoginView.as_view(), name='api-login'),
    path('auth/logout/', LogoutView.as_view(), name='api-logout'),
    path('auth/me/', MeView.as_view(), name='api-me'),
    path('app/bootstrap/', AppBootstrapView.as_view(), name='api-app-bootstrap'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='api-dashboard-stats'),
    path('fhir/', FHIRResourceListView.as_view(), name='api-fhir-list'),
    path('fhir/_versions/', FHIRResourceVersionAuditView.as_view(), name='api-fhir-version-audit'),
    path('fhir/<str:resource_type>/', FHIRResourceListView.as_view(), name='api-fhir-type-list'),
    path('fhir/<str:resource_type>/<str:logical_id>/', FHIRResourceDetailView.as_view(), name='api-fhir-detail'),
    path('fhir/<str:resource_type>/<str:logical_id>/_history/', FHIRResourceHistoryView.as_view(), name='api-fhir-history'),
    path('fhir/<str:resource_type>/<str:logical_id>/_history/<int:version_id>/', FHIRResourceVersionView.as_view(), name='api-fhir-version'),
]
