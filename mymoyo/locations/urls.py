from django.urls import path

from . import views


urlpatterns = [
    path('map/', views.facility_map, name='facility_map'),
    path('map/results/', views.facility_map_results, name='facility_map_results'),
    path('map/road-distances/', views.facility_road_distances, name='facility_road_distances'),
    path('map/directions/', views.facility_directions, name='facility_directions'),
]
