from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AppBootstrapView,
    AppointmentViewSet,
    CsrfTokenView,
    DistrictViewSet,
    FacilityViewSet,
    LoginView,
    LogoutView,
    MeView,
    ProvinceViewSet,
    UserViewSet,
)


router = DefaultRouter()
router.register('appointments', AppointmentViewSet, basename='api-appointments')
router.register('districts', DistrictViewSet, basename='api-districts')
router.register('facilities', FacilityViewSet, basename='api-facilities')
router.register('provinces', ProvinceViewSet, basename='api-provinces')
router.register('users', UserViewSet, basename='api-users')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/csrf/', CsrfTokenView.as_view(), name='api-csrf'),
    path('auth/login/', LoginView.as_view(), name='api-login'),
    path('auth/logout/', LogoutView.as_view(), name='api-logout'),
    path('auth/me/', MeView.as_view(), name='api-me'),
    path('app/bootstrap/', AppBootstrapView.as_view(), name='api-app-bootstrap'),
]
