from django.urls import path

from . import views


urlpatterns = [
    path('manage/', views.location_management, name='location_management'),
    path('services/', views.service_management, name='service_management'),
    path('manage/<str:tab>/', views.location_management, name='location_management_tab'),
    path('manage/<str:tab>/<int:pk>/edit/', views.location_edit, name='location_edit'),
    path('manage/<str:tab>/<int:pk>/delete/', views.location_delete, name='location_delete'),
    path('map/', views.facility_map, name='facility_map'),
    path('map/results/', views.facility_map_results, name='facility_map_results'),
    path('map/road-distances/', views.facility_road_distances, name='facility_road_distances'),
    path('map/directions/', views.facility_directions, name='facility_directions'),
]
